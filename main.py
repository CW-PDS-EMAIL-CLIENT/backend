from concurrent import futures
import grpc
import greet_pb2
import greet_pb2_grpc
from IMAPClient import IMAPClient

imapClient = None

class IMAPClientService(greet_pb2_grpc.IMAPClientServiceServicer):
    def FetchEmails(self, request, context):
        offset = request.offset if request.offset != -1 else None
        limit = request.limit if request.limit != -1 else None

        emails_list = [
            greet_pb2.SummaryEmailResponse(
                id=int(email["id"]),
                sender=email["sender"],
                subject=email["subject"],
                date=email["date"]
            ) for email in imapClient.fetch_emails(offset, limit)
        ]
        return greet_pb2.FetchEmailsResponse(emailsList=emails_list)

    def FetchEmailInfo(self, request, context):
        # Преобразуем ID письма в байты
        email_id = str(request.id).encode()

        email_info = imapClient.fetch_email_info(email_id)
        if not email_info:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Email not found")
            return greet_pb2.FetchEmailInfoResponse()

        return greet_pb2.FetchEmailInfoResponse(
            sender=email_info["sender"],
            to=email_info["to"],
            subject=email_info["subject"],
            date=email_info["date"],
            body=email_info["body"],
            attachments=[att["filename"] for att in email_info["attachments"]]
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    greet_pb2_grpc.add_IMAPClientServiceServicer_to_server(IMAPClientService(), server)
    server.add_insecure_port("localhost:5051")
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    print("Server started on port 5051.")
    imap_server = "imap.mail.ru"
    email_user = "donntu_test@mail.ru"
    email_pass = "wrixCgaMYsqXWmVbBPS7"

    imapClient = IMAPClient(imap_server, email_user, email_pass)
    imapClient.open_connect()

    try:
        serve()
    finally:
        imapClient.close_connect()
