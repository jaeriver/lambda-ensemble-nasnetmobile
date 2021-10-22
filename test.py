import json
import boto3
import numpy as np
from PIL import Image
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.models import load_model
import time

bucket_name = 'imagenet-sample'
model_name = 'mobilenet_v2'
model_path = 'model/' + model_name
model = load_model(model_path, compile=True)

s3 = boto3.resource('s3')
# def download_image(object_path, file_path):
#     s3 = boto3.client('s3')
#     s3.download_file(bucket_name, object_path, file_path)


table_name = 'lambda-ensemble1'
region_name = 'us-west-2'
dynamodb = boto3.resource('dynamodb', region_name=region_name)
table = dynamodb.Table(table_name)


def upload_dynamodb(case_num, acc):
    item_dict = dict([(str(i), str(acc[i])) for i in range(len(acc))])
    item_dict['model_name'] = model_name
    item_dict['case_num'] = case_num
    print(item_dict)
    table.put_item(Item=item_dict)
    # with table.batch_writer() as batch:
    #     batch.put_item(Item=item_dict)
    return True


def read_image_from_s3(filename):
    bucket = s3.Bucket(bucket_name)
    object = bucket.Object(filename)
    response = object.get()
    file_stream = response['Body']
    img = Image.open(file_stream)
    return img


def filenames_to_input(file_list, batchsize):
    imgs = []
    for i in range(batchsize):
        img = read_image_from_s3(file_list[i])
        img = img.resize((224, 224), Image.ANTIALIAS)
        img = np.array(img)

        # batchsize, 224, 224, 3
        img = img.reshape((1, img.shape[0], img.shape[1], img.shape[2]))
        img = preprocess_input(img)
        imgs.append(img)

    batch_imgs = np.vstack(imgs)
    return batch_imgs


def inference_model(batch_imgs):
    pred_start = time.time()
    result = model.predict(batch_imgs)
    pred_time = time.time() - pred_start

    result = np.round(result.astype(np.float64), 8)
    result = result.tolist()

    return result, pred_time


def lambda_handler(event, context):
    file_list = event['file_list']
    batch_size = event['batchsize']
    case_num = event['case_num']
    batch_imgs = filenames_to_input(file_list, batch_size)

    total_start = time.time()
    result, pred_time = inference_model(batch_imgs)
    upload_dynamodb(case_num, result)
    total_time = time.time() - total_start

    return {
        'model_name': model_name,
        'case_num': case_num,
        'batch_size': batch_size,
        'total_time': total_time,
        'pred_time': pred_time,
    }

batchsize = 3
bucket = s3.Bucket(bucket_name)
filenames = [file.key for file in bucket.objects.all() if 'JPEG' in file.key]
event = {'file_list': filenames, 'batchsize': batchsize, 'case_num': str(time.time())}
context = 0
lambda_handler(event, context)
