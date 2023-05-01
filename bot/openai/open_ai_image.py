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
    def create_img(self, query, retry_count=0, session = {}):
        try:
            # 如果没配置接口 域名 则使用原本的
            if not conf().get('mj_host'):
                return self.create_img(query, retry_count)
            # 判断限制
            if conf().get('rate_limit_dalle') and not self.tb4dalle.get_token():
                return False, "请求太快了，请休息一下再问我吧"
            logger.info("[OPEN_AI] mj_create_img image_query={}".format(query))
            # 是不是U操作 U操作不用更新messageid
            isUOperate = False
            # 判断是创建 还是选择图片
            if query in ["U1", "U2", "U3", "U4", "V1", "V2", "V3", "V4"]:
                # 是V操作
                isUOperate = query[0] == "U"
                # 操作图片 判断有没有生成过图片
                task_id = session["task_id"]
                channel_id = session["channel_id"]
                message_id = session["message_id"]
                if (not task_id) or (not channel_id) or (not message_id):
                    return False, "需要先生成图片才能操作"
                # 发送操作图片的请求
                self.mj_send_operate(task_id, channel_id, message_id, operate=query)
            else:
                # 发送创建图片的请求
                # 获取任务id
                task_id = self.mj_send_prompt(query)
            print("获取 taskId 成功", task_id)
            # 根据任务id 轮训接口
            image_url, channel_id, message_id = self.get_img_url_by_task_id(task_id)
            if(not image_url):
                return False, "请求超时或内容审核未通过"
            logger.info("[OPEN_AI] mj_create_img image_url={}".format(image_url))
            return True, image_url, task_id, channel_id, message_id, isUOperate
        except Exception as e:
            logger.exception(e)
            return False, str(e)
    
    # 发送点击操作的指令
    def mj_send_operate(self, task_id, channel_id, message_id, operate):
        response = requests.get(self.mj_host + '/operate?'+
                                'taskId=' + task_id +
                                '&channelId='+ channel_id +
                                '&messageId='+ message_id +
                                '&operateCode='+ operate
        )
        print("mj_send_operate response")
        print(response)
        response_obj = json.loads(response.text)
        data = response_obj["data"]
        print("mj_send_operate data")
        print(data)
        # print(data) # 打印响应内容
        # print(data["taskId"]) # 打印响应内容
        # return data["taskId"]
    # 发送生成图片的指令
    def mj_send_prompt(self, prompt):
        response = requests.get(self.mj_host + '/imagine?prompt=' + prompt +'&signStr='+ self.sign_str)
        print("mj_send_prompt response")
        response_obj = json.loads(response.text)
        data = response_obj["data"]
        print("mj_send_prompt data")
        print(data)
        # print(data) # 打印响应内容
        # print(data["taskId"]) # 打印响应内容
        return data["taskId"]
    def get_img_url_by_task_id(self, task_id):
        is_complete = False
        # 最多十分钟 十分钟超时
        max_timer = 5
        while (not is_complete and max_timer > 0):
            time.sleep(60)
            max_timer = max_timer - 1
            print("轮训获取图片链接", task_id)
            response = requests.get(self.mj_host + '/task-result?taskId=' + task_id)
            print(response.status_code) # 打印响应状态码
            response_obj = json.loads(response.text)
            data = response_obj["data"]["result"]
            is_complete = data["isComplete"]
            if is_complete:
                # imgUrl = data["imgUrl"]
                imgUrl = data["proxyImgUrl"]
                # 压缩图片
                if imgUrl:
                    imgUrl = imgUrl + "?width=1400&height=1400"
                # 已经完成 就返回结果
                return imgUrl, data["channelId"], data["messageId"]
        return "", "", ""
            # print(data) # 打印响应内容
            # print(isComplete) # 打印响应内容