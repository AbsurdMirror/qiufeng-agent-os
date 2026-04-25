import base64
import requests
from typing import Annotated, Optional, Dict, Any, List
from pydantic import Field
from src.qfaos import qfaos_pytool

class BaiduOCRTool:
    """
    百度文字识别 (OCR) 工具类。
    
    集成百度 PP-OCRv5 模型，支持对图片中的文字进行检测与识别。
    需要提供百度的 API_KEY 和 SECRET_KEY。
    """

    def __init__(self, api_key: str, secret_key: str):
        """
        初始化百度 OCR 工具。
        
        Args:
            api_key: 百度智能云应用的 API Key。
            secret_key: 百度智能云应用的 Secret Key。
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self._access_token: Optional[str] = None

    def _get_access_token(self) -> str:
        """获取并缓存百度 API 的 Access Token。"""
        if self._access_token:
            return self._access_token
            
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key
        }
        response = requests.post(url, params=params)
        response.raise_for_status()
        token = response.json().get("access_token")
        if not token:
            raise RuntimeError("无法获取百度 OCR Access Token，请检查 API_KEY 和 SECRET_KEY")
        self._access_token = token
        return token

    @qfaos_pytool(id="tool.ocr.baidu_pp_ocrv5")
    def recognize_text(
        self,
        image_path: Annotated[Optional[str], Field(description="本地图片文件路径，例如 'example.jpg'。与 image_url 二选一")] = None,
        image_url: Annotated[Optional[str], Field(description="图片的完整 URL 地址。与 image_path 二选一")] = None,
        use_doc_orientation: Annotated[bool, Field(description="是否开启文档方向识别（自动矫正 0/90/180/270度）")] = False,
        use_doc_unwarping: Annotated[bool, Field(description="是否开启文本图像矫正（矫正褶皱、倾斜等）")] = False,
        use_textline_orientation: Annotated[bool, Field(description="是否开启文本行方向识别")] = False
    ) -> Annotated[Dict[str, Any], Field(description="包含识别结果的字典，主要字段为 words_result")]:
        """
        使用百度 PP-OCRv5 识别图片中的文字。
        支持本地文件或在线 URL，并提供多种图像矫正增强选项。
        """
        access_token = self._get_access_token()
        request_url = f"https://aip.baidubce.com/rest/2.0/ocr/v1/pp_ocrv5?access_token={access_token}"
        
        payload: Dict[str, Any] = {
            "useDocOrientationClassify": str(use_doc_orientation).lower(),
            "useDocUnwarping": str(use_doc_unwarping).lower(),
            "useTextlineOrientation": str(use_textline_orientation).lower()
        }

        if image_path:
            with open(image_path, "rb") as f:
                img_data = f.read()
                payload["image"] = base64.b64encode(img_data).decode("utf-8")
        elif image_url:
            payload["url"] = image_url
        else:
            return {"error": "必须提供 image_path 或 image_url 其中之一"}

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }

        response = requests.post(request_url, headers=headers, data=payload)
        response.raise_for_status()
        
        result = response.json()
        
        # 简单处理错误信息
        if "error_code" in result:
            return {
                "success": False,
                "error_code": result.get("error_code"),
                "error_msg": result.get("error_msg")
            }
            
        return {
            "success": True,
            "words_count": result.get("words_result_num", 0),
            "words_result": result.get("words_result", []),
            "log_id": result.get("log_id")
        }
