import json
from flask import Response


class MyHTTPException():
    status_code: int
    message: str

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message

    def to_dict(self):  
        return {"status": "error", "message": self.message}
    
    def to_response(self):
        return Response(
            response=json.dumps(self.to_dict()),
            status=self.status_code,
            mimetype="application/json"
        )


