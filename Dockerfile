FROM python:alpine3.19
WORKDIR /usr/src/app
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY polybot .

CMD ["python3", "app.py"]