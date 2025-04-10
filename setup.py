import setuptools

# Read the contents of your README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read dependencies from requirements.txt
# While you *can* do this, it's generally better practice for libraries
# to list dependencies directly in install_requires.
# with open('requirements.txt') as f:
#     install_requires = f.read().splitlines()
# Filter out comments and empty lines if reading from requirements.txt
# install_requires = [req for req in install_requires if req and not req.startswith('#')]

# Define dependencies directly (Recommended for libraries)
install_requires = [
    'websockets>=10.0',
    'numpy',
    'sounddevice',
    ]

setuptools.setup(
    name="voxium",
    version="0.2.0",
    author="Nathan French",
    author_email="nathanmfrench17@gmail.com",
    description="A client library for the Voxium real-time transcription service",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nathanmfrench/voxium-client", 
    packages=setuptools.find_packages(where="."),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    install_requires=install_requires,
)