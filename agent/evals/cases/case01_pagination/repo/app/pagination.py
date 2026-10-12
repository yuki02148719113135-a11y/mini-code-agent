PAGE_SIZE = 10


def paginate(items, page):
    """page は 1 始まり。1ページあたり PAGE_SIZE 件を返す。"""
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    return items[start:end - 1]
