from abc import ABC, abstractmethod


class Repository(ABC):
    '''Интерфейс хранилища. В ЛР №4 MemoryRepository заменяется на SqlRepository.'''

    @abstractmethod
    def get_zone(self, zone): ...

    @abstractmethod
    def get_status(self, zone): ...

    @abstractmethod
    def set_status(self, zone, status): ...

    @abstractmethod
    def list_statuses(self): ...

    @abstractmethod
    def get_shelf(self, shelf_id): ...

    @abstractmethod
    def list_shelves(self): ...

    @abstractmethod
    def register_packet(self, shelf_id, ts): ...

    @abstractmethod
    def save_measurement(self, kind, packet): ...

    @abstractmethod
    def list_measurements(self, limit): ...

    @abstractmethod
    def add_alert(self, type_, severity, source, details): ...

    @abstractmethod
    def list_alerts(self, severity, limit): ...