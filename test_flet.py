import flet as ft
import os

def main(page: ft.Page):
    print("Main called")
    with open("test_trace.log", "w") as f: f.write("Main called\n")
    page.add(ft.Text("Hello, Flet 0.80.5!"))
    page.update()

if __name__ == "__main__":
    print("Starting ft.run")
    ft.run(main)
