#!/usr/bin/env python3
"""Render a responsive portal from the upstream-generated Simplestreams catalog."""
import argparse
import datetime
import hashlib
import html
import json
import os
from pathlib import Path,PurePosixPath
import re


PORTAL_STYLE = """
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:#1f2a24;background:#f6f8f6;font-synthesis:none;--ink:#1f2a24;--muted:#5d6b63;--line:#d7e0da;--soft:#eef3ef;--accent:#176b55;--link:#245e8a;--fresh:#28734f;--warning:#8a5b1c}
*{box-sizing:border-box;letter-spacing:0}
h1,.stat strong,.eyebrow{letter-spacing:0}
body{margin:0}
a{color:var(--link);text-decoration:none}
a:hover{text-decoration:underline}
button,input,select{font:inherit}
button,a,input,select,summary{outline-offset:3px}
button{cursor:pointer}
main,header,footer{max-width:1360px;margin:auto;padding:0 24px}
header{display:flex;justify-content:space-between;align-items:center;gap:20px;padding-top:14px;padding-bottom:14px;border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;color:var(--ink)}
.mark{display:grid;place-items:center;width:34px;height:34px;background:var(--accent);border-radius:8px;color:#fff;font-size:13px}
nav{display:flex;gap:20px;font-size:13px}
.hero{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(360px,.9fr);align-items:center;gap:32px;padding:22px 0 16px}
.eyebrow{color:#527263;font-size:11px;font-weight:650}
h1{font-size:30px;line-height:1.25;margin:8px 0 10px;color:var(--ink)}
h1 span{color:#65746c}
p{color:var(--muted);line-height:1.65;font-size:14px;max-width:560px;margin:0}
.quick{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px 16px}
.quick h2{font-size:13px;margin:0 0 8px;color:#465a50}
.command{display:flex;gap:10px;align-items:center;padding:8px 0;border-top:1px solid #e8eeea}
.command code{font-size:11px;line-height:1.55;overflow-wrap:anywhere;flex:1}
.copy{background:var(--soft);color:#315747;border:1px solid #d9e5dc;border-radius:6px;padding:5px 9px;font-size:11px;flex-shrink:0}
.copy:hover{background:#e1ece4}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;margin:4px 0 18px;border-block:1px solid var(--line)}
.stat{padding:12px 18px;border:0;border-right:1px solid var(--line);border-radius:0;background:transparent}
.stat:last-child{border-right:0}
.stat strong{display:block;font-size:22px;line-height:1.2;margin-bottom:4px;color:var(--ink)}
.stat span{color:var(--muted);font-size:12px}
.catalog{border:0;border-top:1px solid var(--line);border-radius:0;background:transparent;overflow:hidden}
.catalog-head{display:flex;justify-content:space-between;align-items:center;padding:16px 0 12px;gap:12px}
.catalog-head h2{font-size:17px;margin:0;color:var(--ink)}
.count{color:var(--muted);font-size:12px}
.filters{display:grid;grid-template-columns:minmax(220px,1fr) 160px 140px 150px;gap:8px;padding:0 0 12px}
input,select{width:100%;border:1px solid var(--line);border-radius:6px;padding:8px 10px;background:#fff;color:#31483b;font-size:12px}
input::placeholder{color:#7d8b82}
.table-wrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:12px;min-width:850px}
thead{background:#eef2ef;color:#52645a;font-size:11px}
th,td{padding:11px 14px;text-align:left;border-top:1px solid #e5ebe6;vertical-align:top}
td:first-child{min-width:190px}
td:last-child{min-width:165px}
td strong{display:block;font-size:13px;font-weight:600;color:var(--ink)}
small{display:block;color:#738178;font-size:10px;margin-top:5px}
.arch{background:#e8f0f4;color:#315d77;border-radius:4px;padding:3px 6px;font-size:11px}
.badge{display:block;width:max-content;margin-top:5px;font-size:10px;border-radius:4px;padding:2px 6px}
.fresh{background:#e8f3eb;color:var(--fresh)}
.old{background:#f7f0e5;color:var(--warning)}
summary{cursor:pointer;color:var(--link);white-space:nowrap}
details[open]{min-width:300px}
.files{padding:0;margin:8px 0;list-style:none}
.files li{display:grid;grid-template-columns:minmax(0,1fr) max-content;gap:2px 10px;margin:10px 0}
.files span{color:#738178;font-size:10px}
.files code,.fingerprint{grid-column:1/-1;display:block;font:10px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;color:#68776e;max-width:100%;overflow-wrap:anywhere;margin-top:2px}
.empty{padding:28px;text-align:center;color:#66766c}
.notes{padding:12px 0;border-top:1px solid #e5ebe6;color:#738178;font-size:11px;line-height:1.7}
footer{display:flex;justify-content:space-between;gap:16px;font-size:11px;color:#738178;padding-top:18px;padding-bottom:24px}
tr[hidden]{display:none}
@media(max-width:860px){.hero{grid-template-columns:1fr;gap:14px;padding-top:18px}.filters{grid-template-columns:1fr 1fr}.filters input{grid-column:1/-1}.stats{grid-template-columns:1fr 1fr}.stat:nth-child(2){border-right:0}.stat:nth-child(-n+2){border-bottom:1px solid var(--line)}}
@media(max-width:520px){main,header,footer{padding-left:16px;padding-right:16px}header{gap:10px}nav{gap:12px;font-size:12px}.brand{font-size:13px}.mark{width:32px;height:32px}.hero{padding-top:16px}h1{font-size:26px}.quick{padding:10px 12px}.stats{margin-top:4px}.stat{padding:10px 12px}.stat strong{font-size:20px}.catalog-head{padding-top:14px}.filters{gap:7px}.notes{padding:10px 0}footer{flex-direction:column;gap:6px}}
"""


def asset_path(root, value):
    path=PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts or value.startswith('//'):
        raise ValueError('invalid Simplestreams asset path')
    return root.joinpath(*path.parts)


def models(root, flavour, verify_files=True):
    data=json.loads((root/'streams/v1/spiritlhl.json').read_text())
    if data.get('format')!='products:1.0' or not data.get('products'):
        raise ValueError('empty or invalid Simplestreams catalog')
    values=[];now=datetime.datetime.now(datetime.timezone.utc)
    for key,product in sorted(data['products'].items()):
        if not product.get('versions'):raise ValueError('product has no image versions')
        versions=[]
        for stamp,version in sorted(product['versions'].items(),reverse=True):
            built=datetime.datetime.strptime(stamp,'%Y%m%d_%H%M').replace(tzinfo=datetime.timezone.utc)
            if built>now+datetime.timedelta(days=1):raise ValueError('future image timestamp')
            items=version.get('items',{})
            if flavour+'.tar.xz' not in items or not any(i.get('ftype') in ('squashfs','disk-kvm.img') for i in items.values()):
                raise ValueError('incomplete image metadata/rootfs pair')
            files=[]
            for name,item in items.items():
                path=asset_path(root,item['path'])
                if not re.fullmatch('[0-9a-f]{64}',item.get('sha256','')) or item.get('size',0)<=0:
                    raise ValueError('invalid image size or digest')
                if verify_files:
                    if not path.is_file() or path.is_symlink() or path.stat().st_size!=item['size']:
                        raise ValueError('index asset does not match a complete file')
                    with path.open('rb') as stream:
                        if hashlib.file_digest(stream,'sha256').hexdigest()!=item['sha256']:
                            raise ValueError('index digest does not match image bytes')
                files.append({'name':name,'url':'/'+item['path'],'size':item['size'],'sha256':item['sha256']})
            fingerprint=items[flavour+'.tar.xz'].get('combined_squashfs_sha256','')
            versions.append({'stamp':stamp,'date':built.strftime('%Y-%m-%d %H:%M'),'files':files,'fingerprint':fingerprint})
        current=versions[0]
        values.append({'id':key,'distro':product.get('os',product.get('distro','')),'release':product['release'],
                       'arch':product['arch'],'variant':product['variant'],'aliases':product.get('aliases',''),
                       'date':current['date'],'stamp':current['stamp'],
                       'stale':(now-datetime.datetime.strptime(current['stamp'],'%Y%m%d_%H%M').replace(tzinfo=datetime.timezone.utc)).days>8,'versions':versions})
    return values


def render(values,flavour):
    esc=lambda value:html.escape(str(value),quote=True)
    cli='incus' if flavour=='incus' else 'lxc'
    title='Incus' if flavour=='incus' else 'LXD';url=f'https://{flavour}images.spiritlhl.net'
    other='lxd' if flavour=='incus' else 'incus'
    options=lambda key:''.join(f'<option value="{esc(v)}">{esc(v)}</option>' for v in sorted({r[key] for r in values}))
    rows=[]
    for index,row in enumerate(values):
        files=''.join(f'<li><a href="{esc(f["url"])}">{esc(f["name"])}</a><span>{f["size"]/1024**2:.2f} MiB</span><code>{f["sha256"]}</code></li>' for f in row['versions'][0]['files'])
        search=' '.join(str(row[k]) for k in ('distro','release','arch','variant','aliases')).lower()
        state='<span class="badge old">较早构建</span>' if row['stale'] else '<span class="badge fresh">近期构建</span>'
        rows.append(f'<tr data-index="{index}" data-search="{esc(search)}" data-distro="{esc(row["distro"])}" data-arch="{esc(row["arch"])}" data-stamp="{esc(row["stamp"])}"><td><strong>{esc(row["distro"])}</strong><small>{esc(row["aliases"])}</small></td><td>{esc(row["release"])}</td><td><code class="arch">{esc(row["arch"])}</code></td><td>{esc(row["variant"])}</td><td><time>{esc(row["date"])}</time>{state}</td><td><details><summary>文件与校验</summary><ul class="files">{files}</ul><small>镜像指纹</small><code class="fingerprint">{esc(row["versions"][0]["fingerprint"])}</code></details></td></tr>')
    payload=json.dumps(values,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    commands=[f'{cli} remote add spiritlhl {url} --protocol simplestreams --public',f'{cli} image list spiritlhl:',f'{cli} launch spiritlhl:debian/13/cloud my-instance']
    command_html=''.join(f'<div class="command"><code>{esc(c)}</code><button type="button" class="copy" aria-label="复制命令">复制</button></div>' for c in commands)
    content='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>TITLE 镜像源 · spiritlhl</title><style>
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:#17243a;background:#f4f6fa;font-synthesis:none}*{box-sizing:border-box}body{margin:0}a{color:#245caa;text-decoration:none}a:hover{text-decoration:underline}button,input,select{font:inherit}button,a,input,select,summary{outline-offset:4px}button{cursor:pointer}main,header,footer{max-width:1240px;margin:auto;padding:0 28px}header{display:flex;justify-content:space-between;align-items:center;gap:20px;padding-top:24px;padding-bottom:24px}.brand{display:flex;align-items:center;gap:12px;font-weight:700}.mark{display:grid;place-items:center;width:38px;height:38px;background:#173a61;border-radius:10px;color:white;font-size:15px}nav{display:flex;gap:22px;font-size:14px}.hero{display:grid;grid-template-columns:1fr 1fr;align-items:center;gap:36px;padding:32px 0}.eyebrow{color:#53728d;font-size:13px;letter-spacing:.09em;font-weight:650}h1{font-size:40px;letter-spacing:-.03em;margin:14px 0}h1 span{color:#53728d}p{color:#607086;line-height:1.8;font-size:15px;max-width:560px}.quick{background:white;border:1px solid #dbe3ed;border-radius:14px;padding:18px}.quick h2{font-size:14px;margin:0 0 14px;color:#4a607b}.command{display:flex;gap:12px;align-items:center;padding:11px 0;border-top:1px solid #edf0f5}.command code{font-size:12px;line-height:1.6;overflow-wrap:anywhere;flex:1}.copy{background:#edf3f9;color:#294f73;border:0;border-radius:6px;padding:6px 9px;font-size:12px;flex-shrink:0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:16px 0 28px}.stat{border:1px solid #dbe3ed;background:#fff;border-radius:12px;padding:18px 20px}.stat strong{display:block;font-size:26px;margin-bottom:6px;letter-spacing:-.03em}.stat span{color:#718097;font-size:12px}.catalog{background:white;border:1px solid #dbe3ed;border-radius:14px;overflow:hidden}.catalog-head{display:flex;justify-content:space-between;align-items:center;padding:22px 22px 16px;gap:12px}.catalog-head h2{font-size:19px;margin:0}.count{color:#718097;font-size:13px}.filters{display:grid;grid-template-columns:minmax(200px,1fr) 160px 140px 150px;gap:10px;padding:0 22px 20px}input,select{width:100%;border:1px solid #dbe3ed;border-radius:8px;padding:10px 12px;background:#fff;color:#314863;font-size:13px}input::placeholder{color:#8391a5}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px;min-width:870px}thead{background:#f6f8fb;color:#607086;font-size:12px}th,td{padding:15px 20px;text-align:left;border-top:1px solid #e9edf3;vertical-align:top}td:first-child{min-width:210px}td:last-child{min-width:180px}td strong{display:block;font-size:14px;font-weight:600}small{display:block;color:#8a97a8;font-size:11px;margin-top:7px}.arch{background:#edf3fa;color:#355d82;border-radius:5px;padding:4px 7px;font-size:12px}.badge{display:block;width:max-content;margin-top:7px;font-size:10px;border-radius:4px;padding:3px 6px}.fresh{background:#eaf6f0;color:#39795e}.old{background:#f4eee3;color:#8c6b36}summary{cursor:pointer;color:#356c9d;white-space:nowrap}details[open]{min-width:340px}.files{padding:0;margin:12px 0;list-style:none}.files li{margin:12px 0}.files span{float:right;color:#8895a6;font-size:11px}.files code,.fingerprint{display:block;font:10px/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;color:#7d8b9b;max-width:340px;overflow-wrap:anywhere;margin-top:5px}.empty{padding:34px;text-align:center;color:#7b899d}.notes{padding:20px 22px;border-top:1px solid #e9edf3;color:#7b899d;font-size:12px;line-height:1.8}footer{display:flex;justify-content:space-between;gap:16px;font-size:12px;color:#8a97a8;padding-top:24px;padding-bottom:30px}tr[hidden]{display:none}@media(max-width:850px){.hero{grid-template-columns:1fr;gap:18px;padding-top:12px}h1{font-size:34px}.filters{grid-template-columns:1fr 1fr}.filters input{grid-column:1/-1}.stats{grid-template-columns:1fr 1fr}.hero p{max-width:none}}@media(max-width:480px){main,header,footer{padding-left:16px;padding-right:16px}header{gap:10px}nav{gap:12px;font-size:12px}.brand{font-size:13px}.mark{width:32px;height:32px}.catalog-head{padding:18px 14px 14px}.filters{padding:0 14px 16px;gap:8px}.stat{padding:14px}.stat strong{font-size:23px}.stats{gap:10px}.hero{padding-bottom:16px}.quick{padding:14px}footer{flex-direction:column}.notes{padding:16px 14px}details[open]{min-width:280px}.files code,.fingerprint{max-width:280px}}
</style></head><body><header><div class="brand"><span class="mark">OCV</span>spiritlhl / TITLE</div><nav><a href="https://OTHERimages.spiritlhl.net">OTHER_NAME 镜像</a><a href="https://github.com/oneclickvirt/FLAVOUR_images">GitHub ↗</a></nav></header><main><section class="hero"><div><div class="eyebrow">PUBLIC IMAGE REMOTE</div><h1>TITLE 镜像源<span> / Images</span></h1><p>浏览、筛选与下载系统镜像。通过 spiritlhl 远程源启动实例，查看每个镜像的实际构建时间、文件及 SHA256 校验值。</p></div><div class="quick"><h2>连接镜像源</h2>COMMANDS</div></section><section class="stats" aria-label="镜像统计"><div class="stat"><strong>COUNT</strong><span>镜像组合</span></div><div class="stat"><strong>DISTROS</strong><span>系统发行版</span></div><div class="stat"><strong>ARCHES</strong><span>处理器架构</span></div><div class="stat"><strong>RECENT</strong><span>近 8 天构建</span></div></section><section class="catalog"><div class="catalog-head"><h2>镜像目录</h2><span id="result-count" class="count" role="status" aria-live="polite">COUNT 个镜像</span></div><div class="filters"><input id="search" aria-label="搜索镜像" type="search" placeholder="搜索发行版、版本或别名…"><select id="distribution" aria-label="选择发行版"><option value="">全部发行版</option>DISTRO_OPTIONS</select><select id="architecture" aria-label="选择架构"><option value="">全部架构</option>ARCH_OPTIONS</select><select id="sort" aria-label="排序"><option value="name">按发行版排序</option><option value="date">最新构建优先</option></select></div><div class="table-wrap"><table><thead><tr><th scope="col">发行版 / 别名</th><th scope="col">版本</th><th scope="col">架构</th><th scope="col">类型</th><th scope="col">构建时间 · UTC</th><th scope="col">下载</th></tr></thead><tbody id="images">ROWS</tbody></table></div><div id="empty" class="empty" hidden>没有匹配的镜像，请调整筛选条件。</div><div class="notes">构建时间来自镜像元数据。部署刷新不会把旧镜像标为新构建；下载后可用 SHA256 校验文件。已有远程源可直接使用，无需重复添加。</div></section></main><footer><span>© spiritlhl community · oneclickvirt</span><span>目录更新于 GENERATED UTC</span></footer><script id="image-data" type="application/json">PAYLOAD</script><script>
const rows=[...document.querySelectorAll('#images tr')],search=document.querySelector('#search'),distribution=document.querySelector('#distribution'),architecture=document.querySelector('#architecture'),sort=document.querySelector('#sort');function filter(){const query=search.value.trim().toLocaleLowerCase();let count=0;for(const row of rows){row.hidden=!(row.dataset.search.includes(query)&&(!distribution.value||row.dataset.distro===distribution.value)&&(!architecture.value||row.dataset.arch===architecture.value));if(!row.hidden)count++}document.querySelector('#result-count').textContent=count+' / '+rows.length+' 个镜像';document.querySelector('#empty').hidden=count>0;const ordered=[...rows].sort((a,b)=>sort.value==='date'?b.dataset.stamp.localeCompare(a.dataset.stamp):Number(a.dataset.index)-Number(b.dataset.index));for(const row of ordered)document.querySelector('#images').append(row)}for(const element of[search,distribution,architecture,sort])element.addEventListener(element===search?'input':'change',filter);document.querySelectorAll('.copy').forEach(button=>button.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(button.parentElement.querySelector('code').textContent);button.textContent='已复制';setTimeout(()=>button.textContent='复制',1800)}catch{button.textContent='请手动复制'}}));
</script></body></html>'''
    replacements={'TITLE':title,'OTHER_NAME':'LXD' if flavour=='incus' else 'Incus','OTHER':other,'FLAVOUR':flavour,
                  'COMMANDS':command_html,'COUNT':str(len(values)),'DISTROS':str(len({r['distro'] for r in values})),
                  'ARCHES':str(len({r['arch'] for r in values})),'RECENT':str(sum(not r['stale'] for r in values)),
                  'DISTRO_OPTIONS':options('distro'),'ARCH_OPTIONS':options('arch'),'ROWS':''.join(rows),'PAYLOAD':payload,
                  'GENERATED':datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M')}
    # Replace longer placeholders first, avoiding overlapping token names.
    pattern='|'.join(re.escape(token) for token in sorted(replacements,key=len,reverse=True))
    content=content.replace('</style></head>','</style><style>'+PORTAL_STYLE+'</style></head>',1)
    return re.sub(pattern,lambda match:replacements[match.group(0)],content)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path('build'))
    parser.add_argument('--flavour',choices=['incus','lxd'],required=True);parser.add_argument('--skip-file-check',action='store_true')
    args=parser.parse_args();values=models(args.root,args.flavour,verify_files=not args.skip_file_check)
    (args.root/'index.html').write_text(render(values,args.flavour))
    stamp={'schema':1,'flavour':args.flavour,'products':len(values),'source_commit':os.environ.get('GITHUB_SHA','local-preview'),
           'layout_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    source=Path(os.environ.get('RUNNER_TEMP','/nonexistent'))/'stream-source.json'
    if source.is_file():stamp['stream_builder']=json.loads(source.read_text())
    (args.root/'image-portal-build.json').write_text(json.dumps(stamp,indent=2)+'\n')
    print('Validated portal products:',len(values))

if __name__=='__main__':main()
