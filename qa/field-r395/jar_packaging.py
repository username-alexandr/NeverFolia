"""Non-destructive JAR rewrite. Existing signature metadata is never removed.
Only root-level META-INF signature files sign the current JAR. Signed manifest
sections may not be modified; unrelated unsigned additions are permitted.
This preserves signatures, it does not establish publisher trust or re-sign code.
"""
import copy,io,zipfile,unittest

def signed_sections(raw):
    text=raw.decode('utf-8').replace('\r\n','\n').replace('\r','\n')
    unfolded=[]
    for line in text.split('\n'):
        if line.startswith(' '):
            if not unfolded:raise ValueError('Invalid manifest continuation')
            unfolded[-1]+=line[1:]
        else:unfolded.append(line)
    result=set()
    for section in '\n'.join(unfolded).split('\n\n'):
        fields={}
        for line in section.splitlines():
            if not line:continue
            if ': ' not in line:raise ValueError('Invalid manifest field')
            key,value=line.split(': ',1)
            if key in fields:raise ValueError('Duplicate manifest field')
            fields[key]=value
        if 'Name' in fields and any(key.lower().endswith('-digest') for key in fields):
            if fields['Name'] in result:raise ValueError('Duplicate signed manifest name')
            result.add(fields['Name'])
    return result

def rewrite_zip(raw,replacements):
    buffer=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src,zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as dst:
        names=src.namelist()
        if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP entries')
        signatures=[n for n in names if n.startswith('META-INF/') and n.count('/')==1 and n.upper().endswith(('.SF','.RSA','.DSA','.EC'))]
        if signatures:
            if 'META-INF/MANIFEST.MF' not in names:raise ValueError('Signature metadata without manifest')
            protected=signed_sections(src.read('META-INF/MANIFEST.MF'))|set(signatures)|{'META-INF/MANIFEST.MF'}
            forbidden={n for n in replacements if n in protected and (n not in names or replacements[n]!=src.read(n))}
            if forbidden:raise ValueError('Cannot rewrite signed/manifest entries: '+','.join(sorted(forbidden)))
            print('PRESERVED_SIGNATURE_METADATA',signatures,'covered_modified_entries=0',flush=True)
        for info in src.infolist():dst.writestr(copy.copy(info),replacements.get(info.filename,src.read(info)))
        for name in sorted(set(replacements)-set(names)):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;dst.writestr(info,replacements[name])
    value=buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(value)) as z:
        if z.testzip() is not None:raise ValueError('Repacked ZIP CRC failure')
    return value

class Tests(unittest.TestCase):
    def archive(self,entries):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for k,v in entries.items():z.writestr(k,v)
        return out.getvalue()
    def signed(self):return {'META-INF/MANIFEST.MF':b'Manifest-Version: 1.0\r\n\r\nName: covered.class\r\nSHA-256-Digest: abc\r\n\r\n','META-INF/TEST.SF':b'metadata preserved','covered.class':b'old','unsigned.class':b'before'}
    def test_unsigned_change(self):
        raw=self.archive({'a':b'a','b':b'b'});out=rewrite_zip(raw,{'a':b'longer','c':b'new'})
        with zipfile.ZipFile(io.BytesIO(out)) as z:self.assertEqual(z.read('b'),b'b');self.assertEqual(z.read('a'),b'longer')
    def test_preserve_signature_metadata(self):
        entries=self.signed();out=rewrite_zip(self.archive(entries),{'unsigned.class':b'after','new.class':b'new'})
        with zipfile.ZipFile(io.BytesIO(out)) as z:
            for k,v in entries.items():
                if k!='unsigned.class':self.assertEqual(z.read(k),v)
    def test_reject_covered_change(self):
        with self.assertRaises(ValueError):rewrite_zip(self.archive(self.signed()),{'covered.class':b'new'})
    def test_reject_signature_change(self):
        with self.assertRaises(ValueError):rewrite_zip(self.archive(self.signed()),{'META-INF/TEST.SF':b'new'})
    def test_reject_manifest_change(self):
        with self.assertRaises(ValueError):rewrite_zip(self.archive(self.signed()),{'META-INF/MANIFEST.MF':b'new'})
    def test_folded_name(self):self.assertEqual(signed_sections(b'Name: covered.\n class\nSHA-256-Digest: abc\n\n'),{'covered.class'})
    def test_nested_dependency_metadata_not_root_signature(self):
        rewrite_zip(self.archive({'META-INF/dependency/TEST.SF':b'meta','a':b'a'}),{'a':b'b'})
    def test_repeatable_payload(self):
        raw=self.archive({'a':b'a','b':b'unchanged'*1024});out=rewrite_zip(raw,{'a':b'longer'})
        with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertEqual(z.read('b'),b'unchanged'*1024)
        with zipfile.ZipFile(io.BytesIO(out)) as z:self.assertEqual(z.read('b'),b'unchanged'*1024)
if __name__=='__main__':unittest.main(verbosity=2)
