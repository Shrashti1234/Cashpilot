"""Safe validation output: do not echo private codes or financial request bodies."""
from fastapi.responses import JSONResponse


async def safe_validation_error(request,error):
    return JSONResponse(status_code=422,content={'detail':[
        {'loc':item.get('loc',[]),'msg':item.get('msg','Invalid input'),'type':item.get('type','validation_error')}
        for item in error.errors()]})
