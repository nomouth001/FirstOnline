#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re

# newsletter_routes.py 수정
with open('routes/newsletter_routes.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r"url_for\('home'\)", "url_for('index')", content)

with open('routes/newsletter_routes.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed all home references in newsletter_routes.py')

# auth_routes.py의 나머지 home 참조 수정
with open('routes/auth_routes.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = re.sub(r"url_for\('home'\)", "url_for('index')", content)

with open('routes/auth_routes.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed remaining home references in auth_routes.py') 