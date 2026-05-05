def generate_diff(model_output_1, model_output_2):
    """
    生成两个模型输出之间的差异。
    
    参数:
    model_output_1 (str): 第一个模型的输出。
    model_output_2 (str): 第二个模型的输出。
    
    返回:
    dict: 包含差异的字典，包含添加、删除和修改的内容。
    """
    diff = {
        'added': [],
        'removed': [],
        'modified': []
    }
    
    # 将输出分割为行
    output_1_lines = model_output_1.splitlines()
    output_2_lines = model_output_2.splitlines()
    
    # 创建集合以便于比较
    set_1 = set(output_1_lines)
    set_2 = set(output_2_lines)
    
    # 找出添加和删除的行
    diff['added'] = list(set_2 - set_1)
    diff['removed'] = list(set_1 - set_2)
    
    # 找出修改的行
    for line in output_1_lines:
        if line in set_2:
            continue
        for line_2 in output_2_lines:
            if line != line_2 and line in line_2:
                diff['modified'].append((line, line_2))
    
    return diff

def format_diff(diff):
    """
    格式化差异输出为可读字符串。
    
    参数:
    diff (dict): 差异字典。
    
    返回:
    str: 格式化的差异字符串。
    """
    formatted_diff = []
    
    if diff['added']:
        formatted_diff.append("添加的内容:")
        formatted_diff.extend(diff['added'])
    
    if diff['removed']:
        formatted_diff.append("删除的内容:")
        formatted_diff.extend(diff['removed'])
    
    if diff['modified']:
        formatted_diff.append("修改的内容:")
        for original, modified in diff['modified']:
            formatted_diff.append(f"原始: {original} -> 修改: {modified}")
    
    return "\n".join(formatted_diff)