FROM python:3.10

WORKDIR /app

COPY . .

RUN pip install --upgrade pip
RUN pip install tensorflow==2.13.0
RUN pip install -r requirements.txt

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
