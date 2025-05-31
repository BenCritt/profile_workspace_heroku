from django.core.files.uploadhandler import FileUploadHandler, StopUpload, StopFutureHandlers
from django.utils.deconstruct import deconstructible

@deconstructible
class SizeLimitUploadHandler(FileUploadHandler):
    """
    Hard‑abort the connection as soon as the request body exceeds MAX_BYTES.
    """
    MAX_BYTES = 25 * 1024 * 1024       # 25 MB

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bytes_received = 0

    def receive_data_chunk(self, raw_data, start):
        self.bytes_received += len(raw_data)
        if self.bytes_received > self.MAX_BYTES:
            # Tell Django to drop the connection immediately
            raise StopUpload(connection_reset=True)
        return raw_data    # let Django continue buffering

    def file_complete(self, file_size):
        return None        # use default behaviour
