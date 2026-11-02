"""On-demand, foreground-only OCR. No screenshots are stored or sent out."""
import asyncio
import time

from .routing import normalized


async def recognize(image):
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.graphics.imaging import SoftwareBitmap,BitmapPixelFormat,BitmapAlphaMode
    from winrt.windows.storage.streams import DataWriter
    engine=OcrEngine.try_create_from_user_profile_languages()
    if engine is None:raise RuntimeError('O reconhecimento de texto do Windows não está disponível neste idioma.')
    image=image.convert('RGBA')
    writer=DataWriter();writer.write_bytes(image.tobytes('raw','BGRA'))
    bitmap=SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(),BitmapPixelFormat.BGRA8,
        image.width,image.height,BitmapAlphaMode.PREMULTIPLIED)
    result=await engine.recognize_async(bitmap)
    lines=[]
    for line in result.lines:
        words=list(line.words)
        if not words:continue
        left=min(w.bounding_rect.x for w in words);top=min(w.bounding_rect.y for w in words)
        right=max(w.bounding_rect.x+w.bounding_rect.width for w in words)
        bottom=max(w.bounding_rect.y+w.bounding_rect.height for w in words)
        lines.append({'text':line.text,'rect':(left,top,right,bottom)})
    bitmap.close();writer.close()
    return lines


def capture_foreground(hwnd):
    import win32gui
    from PIL import ImageGrab
    if win32gui.GetForegroundWindow()!=hwnd:
        raise RuntimeError('A janela perdeu o foco. Volte ao aplicativo para continuar esse pedido.')
    box=win32gui.GetClientRect(hwnd)
    left,top=win32gui.ClientToScreen(hwnd,(0,0))
    width,height=box[2],box[3]
    if width<100 or height<100:raise RuntimeError('A janela precisa estar visível para conferir o menu.')
    image=ImageGrab.grab(bbox=(left,top,left+width,top+height),all_screens=True)
    if win32gui.GetForegroundWindow()!=hwnd:raise RuntimeError('A janela mudou durante a observação.')
    scale=min(1,1600/width)
    if scale!=1:image=image.resize((round(width*scale),round(height*scale)))
    return image,{'left':left,'top':top,'width':width,'height':height,'scale':scale}


class Screen:
    async def observe(self,hwnd,cancel):
        if cancel.is_set():raise asyncio.CancelledError
        image,geometry=await asyncio.to_thread(capture_foreground,hwnd)
        lines=await recognize(image)
        for line in lines:
            crop=image.crop(tuple(round(v) for v in line['rect'])).convert('RGB')
            pixels=list(crop.getdata())
            line['selected_green']=sum(g>90 and g>r*1.5 and g>b*1.3 for r,g,b in pixels)>max(4,len(pixels)*.025)
        return {'lines':lines,'geometry':geometry,'time':time.monotonic()}

    async def click(self,hwnd,observation,line,cancel):
        if cancel.is_set():raise asyncio.CancelledError
        if time.monotonic()-observation['time']>2:raise RuntimeError('O menu mudou. Vou precisar observar novamente.')
        import win32api,win32con,win32gui
        if win32gui.GetForegroundWindow()!=hwnd:raise RuntimeError('A janela perdeu o foco; nenhum clique foi enviado.')
        g=observation['geometry'];box=win32gui.GetClientRect(hwnd)
        if (box[2],box[3])!=(g['width'],g['height']):raise RuntimeError('O tamanho da janela mudou; nenhum clique foi enviado.')
        if win32gui.ClientToScreen(hwnd,(0,0))!=(g['left'],g['top']):raise RuntimeError('A janela se moveu; nenhum clique foi enviado.')
        rect=line['rect']
        x=round(g['left']+(rect[0]+rect[2])/2/g['scale'])
        y=round(g['top']+(rect[1]+rect[3])/2/g['scale'])
        if not g['left']<=x<g['left']+g['width'] or not g['top']<=y<g['top']+g['height']:
            raise RuntimeError('O controle saiu da janela.')
        win32api.SetCursorPos((x,y))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN,0,0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP,0,0)


def matching_lines(observation,labels,*,upper=None,lower=None):
    result=[]
    height=observation['geometry']['height']*observation['geometry']['scale']
    for line in observation['lines']:
        text=normalized(line['text']).strip(' .:!')
        if not any(text==normalized(label) for label in labels):continue
        middle=(line['rect'][1]+line['rect'][3])/2/height
        if upper is not None and middle>upper:continue
        if lower is not None and middle<lower:continue
        result.append(line)
    return result
