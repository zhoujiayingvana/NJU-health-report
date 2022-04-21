from njupass import NjuUiaAuth
from dotenv import load_dotenv
import os
import json
import time
import logging
import datetime
from pytz import timezone
import ddddocr
from urllib.parse import urlencode

URL_JKDK_LIST = 'http://ehallapp.nju.edu.cn/xgfw/sys/yqfxmrjkdkappnju/apply/getApplyInfoList.do'
URL_JKDK_APPLY = 'http://ehallapp.nju.edu.cn/xgfw/sys/yqfxmrjkdkappnju/apply/saveApplyInfos.do'
URL_JDKD_INDEX = 'http://ehallapp.nju.edu.cn/xgfw/sys/mrjkdkappnju/index.html'
auth = NjuUiaAuth(keep_alive=True)  # 关闭多余的连接，避免多次尝试登陆出错


def get_zjhs_time(method='YESTERDAY'):
    today = datetime.datetime.now(timezone('Asia/Shanghai'))
    yesterday = today + datetime.timedelta(-1)
    if method == 'YESTERDAY':
        return yesterday.strftime("%Y-%m-%d %H")
    else:
        try:
            eval_method = eval(method)
            start_time = datetime.datetime.strptime(
                eval_method['start_time'], "%Y-%m-%d").date()
            interval = int(eval_method['interval'])
            covid_test_time = today - \
                datetime.timedelta((today.date()-start_time).days % interval)
        except Exception as e:
            covid_test_time = yesterday
            log.error(e)
            log.error("设置核酸检测时间为昨日")
        log.info(f'最近核酸检测时间为{covid_test_time.strftime("%Y-%m-%d %H")}')
        return covid_test_time.strftime("%Y-%m-%d %H")


if __name__ == "__main__":
    load_dotenv(verbose=True)
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
    log = logging.getLogger()

    username = os.getenv('NJU_USERNAME')
    password = os.getenv('NJU_PASSWORD')
    curr_location = os.getenv('CURR_LOCATION')
    method = os.getenv('COVID_TEST_METHOD')  # 核酸时间

    if method == '':
        method = 'YESTERDAY'

    if username == '' or password == '' or curr_location == '':
        log.error('账户、密码或地理位置信息为空！请检查是否正确地设置了 SECRET 项（GitHub Action）。')
        os._exit(1)

    log.info('尝试登录...')

    if auth.needCaptcha(username):
        log.error("统一认证平台需要输入验证码，尝试识别...")
        try:
            img = auth.getCaptchaCode().getvalue()  # convert BytesIO to bytes-like object
            ocr = ddddocr.DdddOcr(show_ad=False)
            ocr_res = ocr.classification(img)
            log.info(f"识别验证码：{ocr_res}")
        except ValueError as e:
            log.error(e, "识别接口出错")
            os._exit(1)
    ok = auth.login(username, password, ocr_res)
    if not ok:
        log.error("登录失败，可能是密码错误或网络问题或验证码识别错误，请重试。")
        os._exit(1)

    log.info('登录成功！')
    force_act = False  # 是否强制打卡
    for count in range(10):
        log.info('尝试获取打卡列表信息...')
        r = auth.session.get(URL_JKDK_LIST)
        if r.status_code != 200:
            log.error('获取失败，一分钟后再次尝试...')
            time.sleep(60)
            continue

        dk_info = json.loads(r.text)['data'][0]
        if dk_info['TBZT'] == "0" or force_act == True:
            force_act = False
            wid = dk_info['WID']
            param = {
                'WID': wid,
                'IS_TWZC': 1,  # 是否体温正常
                'CURR_LOCATION': curr_location,  # 位置
                'ZJHSJCSJ': get_zjhs_time(method=method),  # 最近核酸检测时间
                'JRSKMYS': 1,  # 今日苏康码颜色
                'IS_HAS_JKQK': 1,  # 健康情况
                'JZRJRSKMYS': 1,  # 居住人今日苏康码颜色
                'SFZJLN': 0
            }
            headers = {
                'referer': URL_JDKD_INDEX,  # required since 2022/4/20
                "X-Requested-With": "com.wisedu.cpdaily.nju",
                "User-Agent": "Mozilla/5.0 (Linux; Android 11; M2006J10C Build/RP1A.200720.011; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/92.0.4515.131 Mobile Safari/537.36 cpdaily/8.2.7 wisedu/8.2.7"
            }
            url = URL_JKDK_APPLY + '?' + urlencode(param)
            log.info('正在打卡')
            auth.session.get(url, headers=headers)
            time.sleep(1)
        else:
            log.info("今日已打卡！")
            os._exit(0)

    log.error("打卡失败，请尝试手动打卡")
    os._exit(-1)
