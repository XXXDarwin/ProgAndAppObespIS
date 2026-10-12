# iot_server/services/errors.py
class UnknownZone(Exception):
    pass


class UnknownShelf(Exception):
    pass


class DuplicatePacket(Exception):
    pass