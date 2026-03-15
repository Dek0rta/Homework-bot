/**
 * Compresses an image File to a base64 JPEG data-URI.
 * Keeps images ≤ maxDim px on the longest side at the given JPEG quality.
 * Used before uploading photos to keep SQLite DB size manageable.
 */
export function compressToBase64(
  file: File,
  maxDim  = 1024,
  quality = 0.78,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = () => {
      URL.revokeObjectURL(url);

      let { naturalWidth: w, naturalHeight: h } = img;
      if (w > maxDim || h > maxDim) {
        if (w >= h) { h = Math.round((h / w) * maxDim); w = maxDim; }
        else        { w = Math.round((w / h) * maxDim); h = maxDim; }
      }

      const canvas = document.createElement('canvas');
      canvas.width  = w;
      canvas.height = h;
      const ctx = canvas.getContext('2d');
      if (!ctx) { reject(new Error('canvas context unavailable')); return; }

      ctx.drawImage(img, 0, 0, w, h);
      resolve(canvas.toDataURL('image/jpeg', quality));
    };

    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('image load failed')); };
    img.src = url;
  });
}
