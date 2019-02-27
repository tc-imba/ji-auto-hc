import csv
import json
import os
import subprocess
import shlex
from urllib import request
import re

from bs4 import BeautifulSoup
import click
import jinja2


def read_students(students):
    result = dict()
    reader = csv.reader(students)
    for row in reader:
        result[str(row[1])] = row[0]
    return result


def parse_moss_result(moss_url):
    def get_student_id(data):
        return data.contents[0].split('/')[-2]

    def get_submission_url(data):
        return data['href']

    def get_percentage(data):
        return data.contents[0].split('/')[-1].strip('()% ')

    with request.urlopen(moss_url) as html:
        soup = BeautifulSoup(html, 'lxml')
        matches = soup.find_all('tr')[1:]
        for match in matches:
            submissions = match.find_all('a')
            left_id = get_student_id(submissions[0])
            right_id = get_student_id(submissions[1])
            a = get_percentage(submissions[0])
            print(left_id, right_id, a)
            # print(match)
        # print(matches[0].a.contents[0])


@click.command()
@click.option('-o', '--output', default='output', show_default=True, type=click.Path(),
              help='Honor council letters output directory')
@click.option('-i', '--input', required=True, type=click.File())
@click.option('-t', '--template', default='template.tex', show_default=True, type=click.File())
@click.option('-s', '--students', type=click.File())
def main(input, output, template, students):
    """A tool automatically sending someone to the honor council."""
    if not os.path.exists(output):
        os.mkdir(output)

    config = json.load(input)
    if 'students' not in config:
        config['students'] = dict()

    if students:
        config['students'].update(read_students(students))

    def form_student(student_id):
        return {
            'name': config['students'].get(str(student_id), None),
            'id': student_id
        }

    # print(config['students'])

    template = jinja2.Template(template.read())

    for case in config['cases']:
        result = parse_moss_result(case['moss'])

        # print(html.read())

        return

        for match in case['matches']:
            students = map(form_student, match['students'])
            with open(os.path.join(output, '1.tex'), 'w') as file:
                file.write(template.render(
                    info=config['info'],
                    reporter=config['reporter'],
                    students=students,
                    case=case,
                    match=match,
                ))
            command = 'xelatex -shell-escape -synctex=1 -interaction=nonstopmode %s -cd' % os.path.join(output, '1.tex')
            subprocess.run(shlex.split(command))

    # print(template.render(**config))
    # print(config['course'])
    pass


if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    main()
