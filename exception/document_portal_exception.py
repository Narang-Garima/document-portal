import inspect
import sys


class DocumentPortalException(Exception):
    def __init__(self, error_message: str, error_detail=sys):

        self.error_message = error_message

        if error_detail is not None:
            _, _, exc_tb = error_detail.exc_info()

            if exc_tb:
                self.file_name = exc_tb.tb_frame.f_code.co_filename
                self.line_number = exc_tb.tb_lineno
            else:
                self.file_name = "unknown"
                self.line_number = -1

        else:
            # capture current call location
            frame = inspect.currentframe().f_back

            self.file_name = frame.f_code.co_filename
            self.line_number = frame.f_lineno

        super().__init__(self.error_message)

    def __str__(self):
        return f"Error in [{self.file_name}] at line [{self.line_number}]: {self.error_message}"
