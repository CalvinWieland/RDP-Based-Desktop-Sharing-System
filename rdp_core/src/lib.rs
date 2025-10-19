use scrap::{Capturer, Display}; // From Scrap linbrary. We import Display to find a monitor and Capturer to grab images from it.

use std::io::ErrorKind::WouldBlock; // Scrap sometimmes returns a type WouldBlock error when it isn't ready to give us a new frame, 
// we import this error to check for that.

use std::ptr; // Import that standard library's pointer tools, we want access to ptr::null_mut(), which let's us return a null or empty pointer
// if something goes wrong.

use fast_image_resize as fr; // Import fast_image_resize library, we give it the alias 'fr' to make the code cleaner.

use std::num::NonZeroU32; // The resizing library requires image dimensions to be non-zero for safety...this type guarantees that the number isn't zero.

use image::{ImageBuffer, Rgb}; // Import ImageBuffer, a generic structure for holding image data and Rgb, a specific type that tells the buffer its pixels
// are in Red-Blue-Green format.

#[repr(C)] // Command to the Rust compiler, meaning "Arrange this struct in memory exactly like a C compiler would"
// Important because when our Python script creates its version of this struct, the memory layout will match perfectly.
pub struct RawImage {
    pub data: *mut u8, // Public field 'data' of type '*mut u8', which is a mutatable raw pointer to an 8-unsigned interger pointing
    // to the start of our JPEG image data.
    pub len: usize, // Public field 'len' of type 'usize', a Rust native size for memory indexing. It holds the number of bytes in our JPEG data.
}

#[unsafe(no_mangle)] // Tells the compiler not to change the function's name, so Python can find it as 'capture_and_encode'.
// 'unsafe()' is required for Rust to acknowledge this attribute as part of an unsafe foreign function interface (FFI).
pub unsafe extern "C" fn capture_and_encode(target_w: u32, target_h: u32) -> *mut RawImage { 
    // unsafe: Declares this function has special requirements that the Rust compiler can't verify (in our case, dealing with pointers).
    // extern "C": Makes it use the C language's calling convention, the universal standard that ctypes understand.
    // target_w and target_h: Are the desired width and height for the output image, sent from Python.
    // return type: This function will return a mutable raw pointer to our RawImage struct.

    // 1. Capture the screen.
    // Logic: This block finds the primary monitor and creates a capturer for it. '.expect()' is a shortcut that will crash the program with a helpful message 
    // if something fails. We also get the native width and height of our screen.
    let display = Display::primary().expect("Couldn't find primary display.");
    let mut capturer = Capturer::new(display).expect("Couldn't begin capture.");
    let (w, h) = (capturer.width(), capturer.height());

    // Logic: capturing a frame might not happen instantly. This loop continuously tries to grab a frame.
    let frame = loop {
        match capturer.frame() { // Rust's pattern matching.
            Ok(frame) => break frame, // If we successfully get a frame, we break out of the loop and return the frame data.
            Err(error) if error.kind() == WouldBlock => continue, // If we get an error, but it is the specific 'WouldBlock' error, 
            // we just continue the loop and try again.
            Err(_) => return ptr::null_mut(), // If we get any other error, something is wrong so we return a null pointer to signal failure to Python.
        }
    };

    // 2. Create a source image from the raw BGRA frame data.
    // Logic: we prepare the captured frame for the resizing library. The fast_image_resize API requires the data be in a Vec<u8> (a growable list of bytes),
    // so we use frame.to_vec() to covert it. PixelType::U8x4 tells the library that our pixels are in 4-byte chunks (like Blue, Green, Red, Alpha).
    let src_image = fr::Image::from_vec_u8(
        NonZeroU32::new(w as u32).unwrap(),
        NonZeroU32::new(h as u32).unwrap(),
        frame.to_vec(),
        fr::PixelType::U8x4,
    ).unwrap();

    // 3. Resize if needed.
    // Logic: Our dynamic resolution logic. If Python sent a width and a height greater than 0, we execute the resizing code. Otherwise, we just use the 
    // original image data and dimensions. The result is a tuple containing the final pixel data and its dimensions.
    let (final_pixel_data, final_w, final_h) = if target_w > 0 && target_h > 0 {
        let mut dst_image = fr::Image::new(
            NonZeroU32::new(target_w).unwrap(),
            NonZeroU32::new(target_h).unwrap(),
            fr::PixelType::U8x4,
        );
        let mut resizer = fr::Resizer::new(fr::ResizeAlg::Nearest);
        resizer.resize(&src_image.view(), &mut dst_image.view_mut()).unwrap();
        (dst_image.into_vec(), target_w, target_h)
    } else {
        (src_image.into_vec(), w as u32, h as u32)
    };

    // 4. Convert to RGB and package into an ImageBuffer.
    // Logic: Crucial data information.
    // 'chuncks_exact(4)' Groups the pixel data into blocks of 4 bytes (B, G, R, A).
    // '.flat_map(|bgra| [bgra[2], bgra[1], bgra[0]])': for each 4 byte chunk, creates a new 3 byte chunk, reordering the bytes from BGRA to RGB.
    // turbojpeg requires RGB format
    // '.collect()': Gathers all the new 3-byte chunks imto a single Vec<u8>.
    let rgb_pixels: Vec<u8> = final_pixel_data
        .chunks_exact(4)
        .flat_map(|bgra| [bgra[2], bgra[1], bgra[0]])
        .collect();

    // Logic: The turbojpeg library (with the image feature) wants data in a structured ImageBuffer. We create one here. 
    // 'ImageBuffer<Rgb<u8>, Vec<u8>>' is a type annotation. Explicitly telling the compiler that this is an image buffer containing rgb pixels, where
    // each color channel is a u8, and the data is stored in a Vec<u8>
    let image_buf: ImageBuffer<Rgb<u8>, Vec<u8>> = ImageBuffer::from_vec(final_w, final_h, rgb_pixels)
        .expect("Failed to create image buffer.");
    
    // 5. Compress the ImageBuffer to JPEG
    // Logic: We call the compression function, passing it our structured image buffer, a quality setting(90), and a color subsampling method(a compress detail)
    let jpeg_data = turbojpeg::compress_image(
        &image_buf, 
        90, 
        turbojpeg::Subsamp::Sub2x2
    ).expect("Failed to compress JPEG.");

    
    // 6. Allocate memory and return pointer.
    // Logic: Handing memory over to Python.
    let mut jpeg_vec = jpeg_data.to_vec(); // We get our compressed data into a mutable Vec.
    let image_box = Box::new(RawImage { // We create our RawImage struct on the heap (using Box), getting a pointer to the start of the JPEG data and its length. 
        data: jpeg_vec.as_mut_ptr(), 
        len: jpeg_vec.len(),
    });
    std::mem::forget(jpeg_vec); // We tell Rust's memory manager: "do not clean up the jpeg_vec data when this function ends", otherwise Python would be left
    // with a pointer to freed memory.
    Box::into_raw(image_box) // We convert the Box (a smart pointer) into a raw pointer and return it. Completing memory handoff to Python.
}
// Finally, the cleanup function: free_image()
//Logic: This function takes back the memory pointer from Python.
// At the end of the fn, Rust's memory manager sees the image_box and the Vec are no longer in use, and it automatically frees all the memory (prevents mem. leak).
#[unsafe(no_mangle)]
pub unsafe extern "C" fn free_image(image_ptr: *mut RawImage){
    if !image_ptr.is_null(){ //safety check to prevent crashing, in case Python sends a null poiter.
        unsafe{
            let image_box = Box::from_raw(image_ptr); // Take the raw pointer and turn it back into a Box, reclaiming Rust ownership of the RawImage struct memory.
            let _ = Vec::from_raw_parts(image_box.data, image_box.len, image_box.len); // We then use the pointer and the length from the struct to reclaim
            // Rust ownership of the JPEG data itself.
        }
    }
}

