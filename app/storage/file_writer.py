def save_llms_txt(content: str):

    with open(
        "outputs/llms.txt",
        "w",
        encoding="utf-8"
    ) as file:

        file.write(content)