import zipfile, re

p = r'D:\寻物星图\寻物星图_详细开发需求文档_V1.0.docx'
z = zipfile.ZipFile(p)
xml = z.read('word/document.xml').decode('utf-8')

xml = xml.replace('</w:p>', '\n')
text = re.sub(r'<[^>]+>', '', xml)
text = re.sub(r'\n{2,}', '\n', text)
print(text)