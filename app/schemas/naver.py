from pydantic import BaseModel


class NaverBlogItem(BaseModel):
    title: str
    description: str
    link: str


class NaverBlogSearchResult(BaseModel):
    items: list[NaverBlogItem]
    total: int
