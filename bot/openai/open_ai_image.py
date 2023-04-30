import time
import openai
import openai.error
from common.token_bucket import TokenBucket
from common.log import logger
from config import conf
import requests
import json

# OPENAI提供的画图接口
class OpenAIImage(object):
    def __init__(self):
        openai.api_key = conf().get('open_ai_api_key')
        if conf().get('rate_limit_dalle'):
            self.tb4dalle = TokenBucket(conf().get('rate_limit_dalle', 50))
        # 初始化host
        self.mj_host = conf().get('mj_host')
        self.sign_str = conf().get('sign_str')
            
    def old_create_img(self, query, retry_count=0):
        try:
            if conf().get('rate_limit_dalle') and not self.tb4dalle.get_token():
                return False, "请求太快了，请休息一下再问我吧"
            logger.info("[OPEN_AI] image_query={}".format(query))
            response = openai.Image.create(
                prompt=query,    #图片描述
                n=1,             #每次生成图片的数量
                size="1024x1024"   #图片大小,可选有 256x256, 512x512, 1024x1024
            )
            image_url = response['data'][0]['url']
            logger.info("[OPEN_AI] image_url={}".format(image_url))
            return True, image_url
        except openai.error.RateLimitError as e:
            logger.warn(e)
            if retry_count < 1:
                time.sleep(5)
                logger.warn("[OPEN_AI] ImgCreate RateLimit exceed, 第{}次重试".format(retry_count+1))
                return self.create_img(query, retry_count+1)
            else:
                return False, "提问太快啦，请休息一下再问我吧"
        except Exception as e:
            logger.exception(e)
            return False, str(e)
    # 使用mj 生成图片
    def create_img(self, query, retry_count=0):
        try:
            # 如果没配置接口 域名 则使用原本的
            if not conf().get('mj_host'):
                return self.create_img(query, retry_count)
            # 判断限制
            if conf().get('rate_limit_dalle') and not self.tb4dalle.get_token():
                return False, "请求太快了，请休息一下再问我吧"
            logger.info("[OPEN_AI] mj_create_img image_query={}".format(query))
            # 发送创建图片的请求
            # 获取任务id
            task_id = self.mj_send_prompt(query)
            print("获取taskid 成功", task_id)
            # 根据任务id 轮训接口
            image_url = self.get_img_url_by_task_id(task_id)
            logger.info("[OPEN_AI] mj_create_img image_url={}".format(image_url))
            return True, image_url
        except Exception as e:
            logger.exception(e)
            return False, str(e)
    # 发送生成图片的指令
    def mj_send_prompt(self, prompt):
        response = requests.get(self.mj_host + '/imagine?prompt=' + prompt +'&signStr='+ self.sign_str)
        print("mj_send_prompt response")
        print(response)
        response_obj = json.loads(response.text)
        data = response_obj["data"]
        print("mj_send_prompt data")
        print(data)
        # print(data) # 打印响应内容
        # print(data["taskId"]) # 打印响应内容
        return data["taskId"]
    def get_img_url_by_task_id(self, task_id):
        is_complete = False
        while not is_complete:
            time.sleep(5)
            print("轮训获取图片链接", task_id)
            response = requests.get(self.mj_host + '/task-result?taskId=' + task_id)
            # print(response.status_code) # 打印响应状态码
            response_obj = json.loads(response.text)
            data = response_obj["data"]["result"]
            is_complete = data["isComplete"]
            if is_complete:
                # 已经完成 就返回结果
                return data["imgUrl"]
            
            # print(data) # 打印响应内容
            # print(isComplete) # 打印响应内容