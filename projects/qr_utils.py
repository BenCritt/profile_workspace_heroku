import qrcode
import io

def generate_qr_code_image(data):
    """
    Generates a QR code from text data and returns it as a BytesIO stream.
    Does not save to disk, keeping the operation strictly in memory.
    """
    # 1. Generate QR Object
    qr = qrcode.QRCode(
        version=1, 
        box_size=10, 
        border=5
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    # 2. Create Image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # 3. Save to In-Memory Buffer
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    
    # Rewind the buffer to the beginning so it can be read by HttpResponse
    buffer.seek(0)
    
    return buffer