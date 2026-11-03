"""Export an existing local server library for browser import; never exports passwords."""
from pathlib import Path
import argparse
import json
import sqlite3
import struct
import uuid
import zipfile
from datetime import datetime, timezone
import mimetypes

def export(root: Path, destination: Path):
    root=root.resolve(); db=root/'.photojoy/photojoy.sqlite3'
    destination.mkdir(parents=True,exist_ok=True)
    backup=destination/f'photojoy-before-pages-{datetime.now():%Y%m%d-%H%M%S}.sqlite3'
    with sqlite3.connect(db) as original, sqlite3.connect(backup) as copy:
        original.backup(copy)
    con=sqlite3.connect(backup); con.row_factory=sqlite3.Row
    rows=lambda sql:[dict(row) for row in con.execute(sql)]
    records=[]; blobs={}
    def record(table,id,value): records.append({'table':table,'id':id,'value':value})
    def blob(table,id,path,file_name=None):
        path=Path(path).resolve()
        if not path.is_relative_to(root) or not path.is_file(): raise ValueError(f'Missing library file: {table}/{id}')
        key=f'blobs/{uuid.uuid4().hex}.dat';blobs[key]=path
        records.append({'table':table,'id':id,'blob':key,'name':file_name,'type':mimetypes.guess_type(file_name or path.name)[0] or 'application/octet-stream','lastModified':int(path.stat().st_mtime*1000)})
    def vector(row): return list(struct.unpack('<'+'f'*row['dimension'],row['embedding']))
    for child in rows('SELECT * FROM children'):
        record('children',child['id'],{'id':child['id'],'name':child['name'],'group_name':child['group_name'],'archived':not bool(child['active'])})
    media_rows=rows('SELECT * FROM media')
    for m in media_rows:
        mid=m['id'];name=Path(m['path']).name;faces=[]
        for f in rows(f"SELECT * FROM faces WHERE media_id='{mid}'"):
            fid=f['id'];preview='legacy-'+fid
            blob('crops',fid,f['crop']);blob('previews',preview,f['preview'])
            candidate=json.loads(f['candidate'])
            faces.append({'id':fid,'bbox':json.loads(f['bbox']),'embedding':vector(f),'frame':f['frame'],'previewId':preview,'candidate':candidate,'pixelSize':0 if candidate['reason'].startswith('작은 얼굴') else 100,'quality':{'usable':True,'source':'기존 서버 특징; 품질 재측정은 원본 재분석 시 수행'}})
        preview='legacy-media-'+mid if m['thumbnail'] else None
        if preview:blob('previews',preview,m['thumbnail'])
        blob('originals',mid,m['path'],name)
        state='organized' if m['status']=='confirmed' else 'excluded' if m['status']=='excluded' else 'failed' if m['status']=='error' else 'review'
        value={'id':mid,'hash':m['sha256'],'name':name,'kind':m['kind'],'captured':m['captured'][:10],'date_source':m['date_source'],'state':state,'children':json.loads(m['assignments']),'faces':faces,'previewId':preview,'needsReview':state in ('review','failed'),'userChecked':bool(m['reviewed']),'error':m['error'],'history':[],'created':int(datetime.fromisoformat(m['created']).timestamp()*1000),'schema':5,'paths':[],'diagnostics':[{'importedFrom':'PhotoJoy local web 0.3','engine':m['engine']}]}
        for c in rows(f"SELECT * FROM corrections WHERE media_id='{mid}' AND undone=0 ORDER BY rowid"):
            old=json.loads(c['before_json']);prior={**value,'history':[],'children':json.loads(old['assignments']),'userChecked':bool(old['reviewed']),'state':'organized' if old['status']=='confirmed' else 'excluded' if old['status']=='excluded' else 'review','needsReview':old['status'] not in ('confirmed','excluded')}
            value['history'].append({'before':prior,'reason':'기존 서버 교정','created':int(datetime.fromisoformat(c['created']).timestamp()*1000)})
        record('media',mid,value)
    for r in rows('SELECT * FROM reference_faces'):
        crop='legacy-ref-'+r['id'];blob('crops',crop,r['crop'])
        record('references',r['id'],{'id':r['id'],'child':r['child_id'],'embedding':vector(r),'cropId':crop,'sourceHash':r['source_hash'],'active':bool(r['active']),'origin':'기존 서버 사용자 참고 얼굴','engine':r['engine']})
    con.close()
    base={'format':'PhotoJoy-portable-v1','created':datetime.now(timezone.utc).isoformat(),'model':'YuNet-2023mar/SFace-2021dec','records':records}
    groups=[];group=[];size=0
    for key,path in blobs.items():
        if group and size+path.stat().st_size>64*1024*1024:groups.append(group);group=[];size=0
        group.append((key,path));size+=path.stat().st_size
    if group:groups.append(group)
    paths=[]
    for index,group in enumerate(groups,1):
        keys={k for k,_ in group};manifest={**base,'part':index,'parts':len(groups),'records':[r for r in records if 'blob' not in r or r['blob'] in keys]}
        path=destination/f'PhotoJoy-기존자료-{index:02d}.zip'
        with zipfile.ZipFile(path,'w',zipfile.ZIP_STORED) as archive:
            archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
            for key,source in group:archive.write(source,key)
        paths.append(str(path))
    return {'children':len([r for r in records if r['table']=='children']),'media':len(media_rows),'references':len([r for r in records if r['table']=='references']),'archives':paths,'database_backup':str(backup)}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('library',type=Path);parser.add_argument('destination',type=Path);args=parser.parse_args()
    print(json.dumps(export(args.library,args.destination),ensure_ascii=False,indent=2))
