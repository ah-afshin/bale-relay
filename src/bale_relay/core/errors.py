class ServiceError(Exception):
    def __init__(self, message, status=502, detail=None):
        super().__init__(message)
        self.message, self.status, self.detail = message, status, detail
