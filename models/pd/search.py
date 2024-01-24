from typing import List, Optional
from pydantic import BaseModel


class SearchRequestModel(BaseModel):
    search_keyword: str
    count: int

    class Config:
        orm_mode = True


class SearchRequestsListModel(BaseModel):
    searches: List[SearchRequestModel]



class SearchDataModel(BaseModel):
    keywords: Optional[List[str]]
    tag_ids: Optional[List[int]]