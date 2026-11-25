import json
from models.task import Task, ParsedRequest
from pydantic import ValidationError

#任務解析和驗證
def parse_task(fake_llm_response: dict) -> ParsedRequest:
    """
    將使用者輸入轉換成 Task。
    目前使用假資料模擬 LLM 的輸出。
    """

    result_data = json.loads(json.dumps(fake_llm_response))

    try:
        #驗證模型資料格式
        result = ParsedRequest(**result_data)
        return result
    
    except ValidationError as e:
        print("任務建立失敗：")
        print(e)

        return ParsedRequest(
            tasks=[],
            missing_information=["資料格式有誤"],
            clarification_needed=True
        )
