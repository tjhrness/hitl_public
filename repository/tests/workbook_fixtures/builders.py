from openpyxl import Workbook


def workbook(path, sheets=1):
    book = Workbook()
    for index in range(sheets):
        sheet = book.active if index == 0 else book.create_sheet()
        sheet.title = f"Criterion {index}"
        sheet.append(["Item ID", "Rater: Alice", "Rater: Bob"])
        sheet.append(["Q1", "Yes", "No"])
    book.save(path)
    book.close()
    return path
