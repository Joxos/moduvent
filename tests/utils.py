import sys
from io import StringIO


class CaptureOutput:
    def __enter__(self):
        self.stream = StringIO()
        sys.stdout, self.originalout = self.stream, sys.stdout
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.getlines()
        sys.stdout, self.originalout = self.originalout, sys.stdout

    def getlines(self):
        result = self.stream.getvalue().split("\n")
        self.stream.seek(0)
        self.stream.truncate()
        return result[:-1]  # remove the last empty line
