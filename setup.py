from setuptools import setup, find_packages


setup(
    name="certbot",
    version='0.0.1',
    license='MIT',
    url="https://github.com/praekeltfoundation/certbot",
    description="A robot for managing letsencrypt certs",
    author='Colin Alston',
    author_email='colin@praekelt.com',
    packages=find_packages() + [
        "twisted.plugins",
    ],
    package_data={
        'twisted.plugins': ['twisted/plugins/certbot_plugin.py']
    },
    include_package_data=True,
    install_requires=[
        'Twisted',
        'PyYaml',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX',
        'Programming Language :: Python',
    ],
)
