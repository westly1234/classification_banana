// helpers.ts
type Box = { x:number, y:number, w:number, h:number, conf:number, title:string, id?:string };
const iou = (a:Box, b:Box) => {
  const ax2=a.x+a.w, ay2=a.y+a.h, bx2=b.x+b.w, by2=b.y+b.h;
  const ix=Math.max(0, Math.min(ax2,bx2)-Math.max(a.x,b.x));
  const iy=Math.max(0, Math.min(ay2,by2)-Math.max(a.y,b.y));
  const inter=ix*iy, union=a.w*a.h+b.w*b.h-inter;
  return union>0 ? inter/union : 0;
};

// prev -> next 매칭 + EMA 스무딩
export function matchAndSmooth(prev:Box[], next:Box[], alpha=0.25): Box[] {
  const used = new Set<number>();
  const out:Box[] = [];

  next.forEach((n) => {
    let best = -1, bestIoU = 0;
    prev.forEach((p, i) => {
      if (used.has(i)) return;
      const v = iou(p, n);
      if (v > bestIoU) { bestIoU = v; best = i; }
    });
    if (bestIoU >= 0.2 && best >= 0) { // 매칭됨 → EMA
      const p = prev[best]; used.add(best);
      out.push({
        id: p.id, title: n.title, conf: n.conf,
        x: p.x*(1-alpha)+n.x*alpha,
        y: p.y*(1-alpha)+n.y*alpha,
        w: p.w*(1-alpha)+n.w*alpha,
        h: p.h*(1-alpha)+n.h*alpha,
      });
    } else { // 새 박스
      out.push({ ...n, id: crypto.randomUUID() });
    }
  });

  // 사라진 박스는 완만하게 제거(원하면 keepN프레임 구현)
  return out;
}
