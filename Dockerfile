FROM amazon/aws-cli:latest

COPY main.py /main.py

ENTRYPOINT ["python3", "/main.py"]