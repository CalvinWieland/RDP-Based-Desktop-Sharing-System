use scrap::{Capturer, Display};
use std::io::ErrorKind::WouldBlock;
use std::ptr;

use fast_image_resize as fr;
use std::num::NonZeroU32;

use image::{ImageBuffer, Rgb};

#[repr(C)]
pub struct RawImage {
    pub data: *mut u8,
    pub len: usize,
}

#[unsafe(no_mangle)]
pub extern "C" fn capture_and_encode(target_w: u32, target_h: u32) -> *mut RawImage {
    // 1. Create capturer
    let display = match Display::primary() {
        Ok(d) => d,
        Err(e) => {
            eprintln!("Failed to get primary display: {e}");
            return ptr::null_mut();
        }
    };

    let mut capturer = match Capturer::new(display) {
        Ok(c) => c,
        Err(e) => {
            eprintln!("Failed to create capturer: {e}");
            return ptr::null_mut();
        }
    };

    let (w, h) = (capturer.width() as usize, capturer.height() as usize);

    // 2. Get a frame (blocking until ready)
    let frame = loop {
        match capturer.frame() {
            Ok(frame) => break frame,
            Err(ref e) if e.kind() == WouldBlock => {
                std::thread::sleep(std::time::Duration::from_millis(5));
                continue;
            }
            Err(e) => {
                eprintln!("Capture error: {e}");
                return ptr::null_mut();
            }
        }
    };

    let total_len = frame.len();
    if h == 0 || w == 0 || total_len == 0 {
        eprintln!("Capture got empty frame (w={w}, h={h}, len={total_len})");
        return ptr::null_mut();
    }

    // We EXPECT at least w * h * 4 bytes (BGRA)
    let bytes_per_pixel = 4usize;
    let needed = w
        .checked_mul(h)
        .and_then(|px| px.checked_mul(bytes_per_pixel))
        .unwrap_or(0);

    if needed == 0 || total_len < needed {
        eprintln!(
            "Frame too small: w={w}, h={h}, needed={needed}, got={total_len}"
        );
        return ptr::null_mut();
    }

    // --- Core fix: take EXACTLY w*h*4 bytes, ignore any trailing padding ---
    let clean_buffer: Vec<u8> = frame[..needed].to_vec();
    // ---------------------------------------------------------------------- 

    // 3. Wrap in fast_image_resize Image
    let src_image = match fr::Image::from_vec_u8(
        NonZeroU32::new(w as u32).unwrap(),
        NonZeroU32::new(h as u32).unwrap(),
        clean_buffer,
        fr::PixelType::U8x4,
    ) {
        Ok(img) => img,
        Err(e) => {
            eprintln!("Failed to create src_image for resize: {e}");
            return ptr::null_mut();
        }
    };

    // 4. Optional resize
    let (final_pixel_data, final_w, final_h) = if target_w > 0 && target_h > 0 {
        let mut dst_image = fr::Image::new(
            NonZeroU32::new(target_w).unwrap(),
            NonZeroU32::new(target_h).unwrap(),
            fr::PixelType::U8x4,
        );

        let mut resizer = fr::Resizer::new(fr::ResizeAlg::Nearest);
        if let Err(e) = resizer.resize(&src_image.view(), &mut dst_image.view_mut()) {
            eprintln!("Resize error: {e}");
            return ptr::null_mut();
        }

        (dst_image.into_vec(), target_w, target_h)
    } else {
        let w_u32 = w as u32;
        let h_u32 = h as u32;
        (src_image.into_vec(), w_u32, h_u32)
    };

    // 5. Convert BGRA → RGB for JPEG encoder (Scrap on mac gives BGRA)
    let rgb_pixels: Vec<u8> = final_pixel_data
        .chunks_exact(4)
        .flat_map(|bgra| {
            let b = bgra[0];
            let g = bgra[1];
            let r = bgra[2];
            [r, g, b] // → R, G, B
        })
        .collect();

    let image_buf: ImageBuffer<Rgb<u8>, Vec<u8>> =
        match ImageBuffer::from_vec(final_w, final_h, rgb_pixels) {
            Some(buf) => buf,
            None => {
                eprintln!("Failed to create ImageBuffer (final_w={final_w}, final_h={final_h})");
                return ptr::null_mut();
            }
        };

    // 6. Compress to JPEG (quality 70 for speed)
    let jpeg_data = match turbojpeg::compress_image(
        &image_buf,
        70,
        turbojpeg::Subsamp::Sub2x2,
    ) {
        Ok(data) => data,
        Err(e) => {
            eprintln!("Failed to compress JPEG: {e}");
            return ptr::null_mut();
        }
    };

    let mut jpeg_vec = jpeg_data.to_vec();

    // 7. Build RawImage for FFI
    let image_box = Box::new(RawImage {
        data: jpeg_vec.as_mut_ptr(),
        len: jpeg_vec.len(),
    });

    // Prevent Rust from freeing jpeg_vec; Python will call free_image
    std::mem::forget(jpeg_vec);

    Box::into_raw(image_box)
}

#[unsafe(no_mangle)]
pub extern "C" fn free_image(image_ptr: *mut RawImage) {
    if image_ptr.is_null() {
        return;
    }

    // Reclaim ownership of RawImage
    let image_box: Box<RawImage> = unsafe { Box::from_raw(image_ptr) };

    // Rebuild Vec<u8> so Rust can free the JPEG buffer
    if !image_box.data.is_null() && image_box.len > 0 {
        unsafe {
            let _ = Vec::from_raw_parts(image_box.data, image_box.len, image_box.len);
        }
    }
    // image_box drops here, freeing the struct itself
}
