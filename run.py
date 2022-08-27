from njupass import NjuUiaAuth
from dotenv import load_dotenv
import os
import time
import logging
import datetime
import ast
from pytz import timezone
import ddddocr
from urllib.parse import urlencode

URL_JKDK_LIST = 'http://ehallapp.nju.edu.cn/xgfw/sys/yqfxmrjkdkappnju/apply/getApplyInfoList.do'
URL_JKDK_APPLY = 'http://ehallapp.nju.edu.cn/xgfw/sys/yqfxmrjkdkappnju/apply/saveApplyInfos.do'
URL_JKDK_INDEX = 'http://ehallapp.nju.edu.cn/xgfw/sys/mrjkdkappnju/index.do'
auth = NjuUiaAuth()


def get_zjhs_time(method='YESTERDAY'):
    today = datetime.datetime.now(timezone('Asia/Shanghai'))
    yesterday = today + datetime.timedelta(-1)
    if method == 'YESTERDAY':
        return yesterday.strftime("%Y-%m-%d %H")
    else:
        try:
            eval_method = ast.literal_eval(method)
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

    if method == None:
        method = 'YESTERDAY'

    if username == None or password == None or curr_location == None:
        log.error('账户、密码或地理位置信息为空！请检查是否正确地设置了 SECRET 项（GitHub Action）。')
        os._exit(1)

    login_count = 3
    for _ in range(login_count):
        log.info('登录中...')
        if auth.needCaptcha(username):
            log.error("统一认证平台需要输入验证码，尝试识别...")
            try:
                img = auth.getCaptchaCode().getvalue()  # convert BytesIO to bytes-like object
                ocr = ddddocr.DdddOcr(show_ad=False)
                ocr_res = ocr.classification(img)
                log.info(f"识别验证码：{ocr_res}")
            except ValueError as e:
                log.error(e, "识别接口出错")
                time.sleep(3)
                continue
        ok = auth.login(username, password, ocr_res)
        if not ok:
            log.error('登陆失败，尝试重新登陆...')
            time.sleep(3)
            continue
        log.info('登录成功！')
        break

    if not ok:
        log.error("登录失败，可能是密码错误或网络问题或验证码识别错误，请重试。")
        os._exit(1)

    force_act = False  # 是否强制打卡
    headers = {
        # required since 2022/08/27
        'referer': 'http://ehallapp.nju.edu.cn/xgfw/sys/mrjkdkappnju/index.html',
        "X-Requested-With": "com.wisedu.cpdaily.nju",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 (4471307264)cpdaily/9.0.14  wisedu/9.0.14",
        "Host": "ehallapp.nju.edu.cn",
        'Accept': 'application/json, text/plain, */*',
        'Connection': 'keep-alive',
        # 'Cookie': '_WEU=YYPeO*RV*JBFWmwCl1eWCBiQgd*zpKgi5U0t7huS9g84BOOBORjIg67wN83mxmgf; iPlanetDirectoryPro=I2q7sOb9YI6oRvKaGSUn7n; MOD_AUTH_CAS=MOD_AUTH_ST-6745229-jdc7HmyHj55lF4L1d7Vs1661586472093-KFu1-cas',
        'Accept-Language': 'zh-cn',
        'Accept-Encoding': 'gzip, deflate'
    }
    for _ in range(10):
        log.info('尝试获取打卡列表信息...')
        auth.session.get(URL_JKDK_INDEX)
        r=auth.session.get(URL_JKDK_LIST,headers=headers)

        if r.status_code != 200:
            log.error('获取失败，一分钟后再次尝试...')
            time.sleep(60)
            continue

        dk_info = r.json()['data'][0]
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
                'SFZJLN': 0 # 是否最近离宁
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
