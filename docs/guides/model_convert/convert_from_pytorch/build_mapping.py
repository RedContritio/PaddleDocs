import tempfile
import os
import re
import typing
from typing import TypedDict

whitelist = set(['torch.Tensor.requires_grad_.md'])


mapping_type_set = set(
    [
        # type 1
        '无参数',
        '参数完全一致',
        '仅参数名不一致',
        '仅 paddle 参数更多',
        '仅参数默认值不一致',
        # type 2
        'torch 参数更多',
        # type 3
        '返回参数类型不一致',
        '参数不一致',
        '参数用法不一致',
        # type 4
        '组合替代实现',
        # type 5
        '用法不同：涉及上下文修改',
        # type 6
        '对应 API 不在主框架',
        # type 7
        '功能缺失',
        # hidden
        '可删除',
    ]
)


class DiffMeta(TypedDict):
    torch_api: str
    torch_api_url: typing.Optional[str]
    paddle_api: typing.Optional[str]
    paddle_api_url: typing.Optional[str]
    mapping_type: str
    source_file: str


with tempfile.TemporaryDirectory() as temp_dir:
    print(temp_dir)


def getMetaFromDiffFile(filepath):
    meta_data: DiffMeta = {'source_file': filepath}
    state = 0
    # 0: wait for title
    # 1: wait for torch api
    # 2: wait for paddle api
    # 3: end
    title_pattern = re.compile(r"^## +\[(?P<type>[^\]]+)\] *(?P<torch_api>.+)$")
    torch_pattern = re.compile(
        r"^### +\[ *(?P<torch_api>torch.[^\]]+)\](?P<url>\([^\)]*\))?$"
    )
    paddle_pattern = re.compile(
        r"^### +\[ *(?P<paddle_api>paddle.[^\]]+)\]\((?P<url>[^\)]+)$"
    )

    with open(filepath, 'r') as f:
        for line in f.readlines():
            if not line.startswith('##'):
                continue

            if state == 0:
                title_match = title_pattern.match(line)
                if title_match:
                    mapping_type = title_match['type'].strip()
                    torch_api = title_match['torch_api'].strip()

                    meta_data['torch_api'] = torch_api
                    meta_data['mapping_type'] = mapping_type
                    state = 1
                else:
                    raise Exception(f"Cannot parse title: {line} in {filepath}")
            elif state == 1:
                torch_match = torch_pattern.match(line)

                if torch_match:
                    torch_api = torch_match['torch_api'].strip()
                    torch_url = torch_match['url'] if torch_match['url'] else ''
                    real_url = torch_url.lstrip('(').rstrip(')')
                    if meta_data['torch_api'] != torch_api:
                        raise Exception(
                            f"torch api not match: {line} != {meta_data['torch_api']} in {filepath}"
                        )
                    meta_data['torch_api_url'] = real_url
                    state = 2
                else:
                    raise Exception(
                        f"Cannot parse torch api: {line} in {filepath}"
                    )
            elif state == 2:
                paddle_match = paddle_pattern.match(line)

                if paddle_match:
                    paddle_api = paddle_match['paddle_api'].strip()
                    paddle_url = paddle_match['url'].strip()
                    meta_data['paddle_api'] = paddle_api
                    meta_data['paddle_api_url'] = paddle_url
                    state = 3
            else:
                pass

    if state < 2:
        raise Exception(
            f"Unexpected End State at {state} in parsing file: {filepath}, current meta: {meta_data}"
        )

    return meta_data


def process_mapping_index(filename):
    state = 0
    # -1: error
    # 0: wait for table header

    # 1: wait for ignore table seperator
    # 2: wait for expect table content

    # 5: wait for ignore table content
    # 6: wait for expect table content

    column_names = []
    column_count = -1
    table_seperator_pattern = re.compile(r"^ *\|(?P<group> *-+ *\|)+ *$")

    expect_column_names = ['序号', 'PyTorch API', 'PaddlePaddle API', '备注']

    table_row_idx = -1

    with open(filename, 'r') as f:
        for i, line in enumerate(f.readlines()):
            if state < 0:
                break

            content = line.strip()
            if len(content) == 0 or content[0] != '|':
                state = 0
                continue

            columns = content.split('|')
            if len(columns) <= 2:
                raise Exception(
                    f'Table column count must > 0, but found {len(columns) - 2} at line {i+1}: {line}'
                )
            columns = columns[1:-1]

            if state == 0:
                column_names.clear()
                column_names.extend([c.strip() for c in columns])
                column_count = len(column_names)
                if column_names == expect_column_names:
                    state = 2
                    table_row_idx = 1
                    print(f'process mapping table at line {i+1}.')
                else:
                    state = 1
                    print(f'ignore table with {column_names} at line {i+1}.')
            elif state == 1:
                if (
                    not table_seperator_pattern.match(line)
                    or len(columns) != column_count
                ):
                    raise Exception(
                        f"Table seperator not match at line {i+1}: {line}"
                    )
                state = 5
            elif state == 2:
                if (
                    not table_seperator_pattern.match(line)
                    or len(columns) != column_count
                ):
                    raise Exception(
                        f"Table seperator not match at line {i+1}: {line}"
                    )
                state = 6
            elif state == 5:
                if len(columns) != column_count:
                    raise Exception(
                        f"Table content not match at line {i+1}: {line}"
                    )
                # state = 5
            elif state == 6:
                if len(columns) != column_count:
                    raise Exception(
                        f"Table content not match at line {i+1}: {line}"
                    )
                idx_s, torch_api_s, paddle_api_s, mapping_s = columns

                idx = int(idx_s)
                if table_row_idx != idx:
                    raise Exception(
                        f"Table row index [{table_row_idx}] != {idx} at line {i+1}: {line}"
                    )
                table_row_idx += 1

                # state = 6
            else:
                raise Exception(
                    f"Unexpected State at {state} in parsing file: {filename}"
                )

    if state == 5 or state == 6:
        state = 0

    if state != 0:
        raise Exception(
            f"Unexpected End State at {state} in parsing file: {filename}"
        )


if __name__ == '__main__':
    # convert from pytorch basedir
    cfp_basedir = os.path.dirname(__file__)
    # pytorch_api_mapping_cn
    mapping_index_file = os.path.join(cfp_basedir, 'pytorch_api_mapping_cn.md')

    if not os.path.exists(mapping_index_file):
        raise Exception(f"Cannot find mapping index file: {mapping_index_file}")

    process_mapping_index(mapping_index_file)

    exit(0)

    api_difference_basedir = os.path.join(cfp_basedir, 'api_difference')

    mapping_file_pattern = re.compile(r"^torch\.(?P<api_name>.+)\.md$")
    # get all diff files (torch.*.md)
    diff_files = sorted(
        [
            os.path.join(path, filename)
            for path, _, file_list in os.walk(api_difference_basedir)
            for filename in file_list
            if mapping_file_pattern.match(filename)
            and filename not in whitelist
        ]
    )

    metas = [getMetaFromDiffFile(f) for f in diff_files]

    for m in metas:
        if m['mapping_type'] not in mapping_type_set:
            print(m)
            raise Exception(
                f"Unknown mapping type: {m['mapping_type']} in {m['source_file']}"
            )

    print(f"Total {len(metas)} mapping metas")
