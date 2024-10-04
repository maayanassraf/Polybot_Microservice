import telebot
from loguru import logger
import os
import json
import time
import boto3
from telebot.types import InputFile

images_bucket = os.environ['BUCKET_NAME']
queue_name = os.environ['SQS_QUEUE_NAME']
REGION_NAME = os.environ['REGION_NAME']

class Bot:

    def __init__(self, token, telegram_chat_url):
        # create a new instance of the TeleBot class.
        # all communication with Telegram servers are done using self.telegram_bot_client
        self.telegram_bot_client = telebot.TeleBot(token)

        # removes any existing webhooks configured in Telegram servers
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)
        # retrieve the certificate from secretsmanager
        # secretsmanager = boto3.client('secretsmanager', region_name=REGION_NAME)
        # response = secretsmanager.get_secret_value(SecretId='public_key_cert')
        # secret_cert = response['SecretString']

        # sets the webhook URL
        self.telegram_bot_client.set_webhook(url=f'{telegram_chat_url}/{token}/', timeout=60)

        logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')

    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)

    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)

    def is_current_msg_photo(self, msg):
        return 'photo' in msg

    def download_user_photo(self, msg):
        """
        Downloads the photos that sent to the Bot to `photos` directory (should be existed)
        :return:
        """
        if not self.is_current_msg_photo(msg):
            raise RuntimeError(f'Message content of type \'photo\' expected')

        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)
        folder_name = file_info.file_path.split('/')[0]

        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        with open(file_info.file_path, 'wb') as photo:
            photo.write(data)

        return file_info.file_path

    def send_photo(self, chat_id, img_path):
        if not os.path.exists(img_path):
            raise RuntimeError("Image path doesn't exist")

        self.telegram_bot_client.send_photo(
            chat_id,
            InputFile(img_path)
        )

    def handle_message(self, msg):
        """Bot Main message handler"""
        logger.info(f'Incoming message: {msg}')
        self.send_text(msg['chat']['id'], f'Your original message: {msg["text"]}')


class ObjectDetectionBot(Bot):
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')

        if self.is_current_msg_photo(msg):
            photo_path = self.download_user_photo(msg)
            sqs_client = boto3.client('sqs', region_name=REGION_NAME)
            chat_id = msg['chat']['id']

            # upload the downloaded photo to S3
            s3_client = boto3.client('s3')
            img_name = os.path.basename(photo_path)

            try:
                s3_client.upload_file(
                    Bucket=f'{images_bucket}',
                    Key=f'images/{img_name}',
                    Filename=f'{photo_path}'
                )
            except:
                logger.error('An error occurred while trying to download image from s3')

            # sends a job to the SQS queue
            job_message = {'img_name': img_name, 'chat_id': chat_id}
            job_message = json.dumps(job_message)
            try:
                response = sqs_client.send_message(QueueUrl=queue_name, MessageBody=job_message)
                # sends message to the Telegram end-user (e.g. Your image is being processed. Please wait...)
                self.send_text((msg['chat']['id']), text=f'Your image is being processed. Please wait...')
            except:
                logger.error('An error occurred while trying to send message to queue')
                self.send_text((msg['chat']['id']), text=f'Something went wrong. Please try again...')