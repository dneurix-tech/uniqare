from io import BytesIO

from fastapi import HTTPException, UploadFile


MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


def _has_allowed_signature(data: bytes) -> bool:
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (
            len(data) >= 12
            and data.startswith(b"RIFF")
            and data[8:12] == b"WEBP"
        )
        or data.startswith(b"GIF87a")
        or data.startswith(b"GIF89a")
    )


def validated_image_stream(
    image: UploadFile,
    max_size_bytes: int = MAX_IMAGE_SIZE_BYTES,
) -> BytesIO:
    if image.content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, PNG, WEBP, or GIF images are allowed",
        )

    data = image.file.read(max_size_bytes + 1)

    if not data:
        raise HTTPException(
            status_code=400,
            detail="Uploaded image is empty",
        )

    if len(data) > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail="Image size must not exceed 5 MB",
        )

    if not _has_allowed_signature(data):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file content is not a valid image",
        )

    stream = BytesIO(data)
    stream.name = image.filename or "upload-image"
    return stream
