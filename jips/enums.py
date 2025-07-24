import enum

import filetype


class AudioFormat(enum.Enum):
    OGG = "ogg"
    MP3 = "mp3"

    def mimetype(self):
        return filetype.get_type(ext=self.value).mime
