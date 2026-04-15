FROM amazon/aws-cli:latest

RUN dnf install -y tar gzip && dnf clean all && rm -rf /var/cache/dnf

ENV PYTHONUNBUFFERED=1

COPY main.py /main.py

ENTRYPOINT ["python3", "/main.py"]