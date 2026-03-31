from setuptools import find_packages, setup


with open("requirements.txt") as f:
    install_requires = [line.strip() for line in f if line.strip()]


setup(
    name="snrg_whatsapp",
    version="0.0.1",
    description="WhatsApp automations for ERPNext using Meta Cloud API",
    author="SNRG",
    author_email="hello@aerele.in",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
