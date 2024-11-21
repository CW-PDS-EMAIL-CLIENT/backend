import grpc
from secureemail_pb2 import EmptyRequest, ProcessEmailRequest, VerifyEmailRequest, Email, Attachment
from secureemail_pb2_grpc import SecureEmailServiceStub


class SecureEmailClient:
    def __init__(self, server_address: str = "localhost:50051"):
        self.channel = grpc.insecure_channel(server_address)
        self.stub = SecureEmailServiceStub(self.channel)

    def generate_keys(self):
        response = self.stub.GenerateKeys(EmptyRequest())
        return {
            "private_key_sign": response.private_key_sign,
            "public_key_sign": response.public_key_sign,
            "private_key_encrypt": response.private_key_encrypt,
            "public_key_encrypt": response.public_key_encrypt,
        }

    def process_email(self, email_body, attachments, private_key_sign, public_key_encrypt):
        email = Email(
            email_body=email_body,
            attachments=[
                Attachment(filename=att["filename"], content=att["content"]) for att in attachments
            ],
        )
        request = ProcessEmailRequest(
            email=email,
            private_key_sign=private_key_sign,
            public_key_encrypt=public_key_encrypt,
        )
        return self.stub.ProcessEmail(request)

    def verify_email(self, encrypted_email, private_key_encrypt, public_key_sign):
        request = VerifyEmailRequest(
            encrypted_email=encrypted_email,
            private_key_encrypt=private_key_encrypt,
            public_key_sign=public_key_sign,
        )
        return self.stub.VerifyEmail(request)
