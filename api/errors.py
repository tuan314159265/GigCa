class ApiError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code = status, code
        super().__init__(message)
