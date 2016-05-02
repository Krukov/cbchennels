#!/usr/bin/env python
from setuptools import setup

from cbchannels import get_version


setup(
    name='cbchannels',
    version=get_version(),
    packages=['cbchannels'],
    
    url='https://github.com/Krukov/cbchannels',
    download_url='https://github.com/Krukov/cbchannels/tarball/' + get_version(),
    license='MIT',
    author='Dmitry Krukov',
    author_email='glebov.ru@gmail.com',
    description='Class Based Consumers for channels',
    long_description=open('README.rst').read(),
    keywords='',
    requires=[
        'six',
        'channels',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
)