"""Generate the 200 held-out evaluation prompts (100 topics x 2 phrasings)."""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.prompts import make_request  # noqa: E402

TOPICS = """mùa thu ở Hà Nội|người con xa quê nhớ mẹ và khói bếp chiều|mưa đầu mùa với mái hiên, cây khế và tiếng ve
người cha đi biển|tuổi thơ bên dòng sông|một con mèo lười|thành phố lúc 2 giờ sáng|chuyến tàu đêm về miền Trung
cô hàng xóm bán bánh mì|đêm giao thừa xa nhà|tiếng chuông chùa buổi sớm|người lính ở đảo xa|cánh đồng lúa chín
con đò sang sông|chợ nổi miền Tây|ngày đầu tiên đi học|bà ngoại và chiếc quạt nan|nỗi nhớ Sài Gòn khi ở nước ngoài
tình yêu tuổi học trò|lời ru của mẹ|chiếc xe đạp cũ của ba|mùa gặt quê nhà|những ngày cách ly ở nhà
cô giáo vùng cao|con trâu và cánh diều|một buổi chiều bên hồ Tây|hoa sữa cuối thu|người ở lại sau cuộc chia tay
bức thư chưa gửi|ly cà phê sáng|người lái đò già|mùa nước nổi|tiếng đàn bầu trong đêm
lần đầu xa nhà đi làm|hạt gạo quê hương|người mẹ nuôi con một mình|đêm trăng trên sông Hương|làng chài lúc bình minh
phố cổ ngày mưa|chiếc áo dài trắng|một đời làm nghề gánh nước thuê|con chó già chờ chủ|bếp lửa ngày đông
tết quê nội|nụ cười của em bé|sinh nhật một mình|người bán hoa đêm|mưa trên phố Huế
đồng đội cũ gặp lại|quán trọ ven đường|trăng rằm trung thu|giếng nước gốc đa|ngọn đèn dầu thuở xưa
một chiều lỡ hẹn|lập trình viên thức khuya|con robot biết nhớ nhà|mạng xã hội và nỗi cô đơn|nhớ bạn thời sinh viên
khoảng trời quê ngoại|người thương binh|hạ về trên phượng đỏ|ngôi trường làng cũ|tiếng còi tàu xa
cô gái Thái Nguyên hái chè|thuyền ra khơi lúc rạng đông|núi rừng Tây Bắc mùa hoa ban|nắng vàng Đà Lạt|lũ về miền Trung
bà mẹ Việt Nam anh hùng|em bé bán vé số|đêm mất ngủ|khu vườn của ông|chiếc nón lá
người thầy già|cơn bão và mái nhà|đường về quê|tình bạn tri âm|lời xin lỗi muộn màng
tiếng mưa trên mái tôn|mùa xuân đầu tiên của con|người đi tìm hạnh phúc|ngày mẹ đi xa mãi mãi|sóng biển và nỗi nhớ
một mình giữa Sài Gòn|hoa cúc họa mi mùa lạnh|làng nghề gốm|nỗi nhớ người yêu ở xa|đứa con lạc lối trở về
biển đêm thành phố Vũng Tàu|đầu năm xin chữ ông đồ|con cá chép ngày ông Táo|tuổi già bên chiếc radio|buổi sáng trên nông trại
chuyến xe buýt cuối ngày|người bán cá chợ sớm|mùa mưa ở Tây Nguyên|chiếc cầu tre quê|cánh cò trắng|một chiều đứng trên đèo|nồi cơm khói bếp ngày bão""".replace("\n", "|").split("|")

topics = [t.strip() for t in TOPICS if t.strip()]
assert len(topics) >= 100, len(topics)
topics = topics[:100]
out = ROOT / "data" / "test_prompts.jsonl"
with open(out, "w", encoding="utf-8") as f:
    for t in topics:
        f.write(json.dumps({"prompt": make_request(t, 8), "topic": t}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"prompt": make_request(t), "topic": t}, ensure_ascii=False) + "\n")
print(f"wrote {2 * len(topics)} prompts -> {out}")
