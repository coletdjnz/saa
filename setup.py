from distutils.core import setup

with open('requirements.txt') as f:
    requirements = f.read().splitlines()

entry_points = {
    "console_scripts": ["saa=saa.saa:main"]
}

setup(
    name='saa',
    version='20200725-dev',
    author='colethedj',
    author_email='colethedj@protonmail.com',
    packages=['saa', 'saa.plugins', 'saa.plugins.reporting'],
    entry_points=entry_points,
    license='LICENSE.txt',
    description='Stream Auto Archiver - Automatically archive livestreams',
    long_description=open('README.md').read(),
    install_requires=requirements,
    python_requires='>=3.7',
)
