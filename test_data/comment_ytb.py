import yt_dlp
import json

video_url = "https://www.youtube.com/shorts/WqfR22-TpAU"

ydl_opts = {
    'quiet': True,
    'extract_flat': False,
    'getcomments': True,
    # "no_warnings": True
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(video_url, download=False)
    
    # Lấy danh sách bình luận
    comments = info.get('comments', [])
    
    # Lưu ra file JSON
    with open('comments.json', 'w', encoding='utf-8') as f:
        json.dump(comments, f, ensure_ascii=False, indent=4)
        
    print(f"Đã lưu {len(comments)} bình luận!")
