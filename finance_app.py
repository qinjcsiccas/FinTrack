import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
from datetime import datetime, timedelta

# --- 页面配置 ---
st.set_page_config(page_title="Jincheng's 财务看板", layout="wide")
st.markdown("""<style> .main { background-color: #f5f7f9; } </style>""", unsafe_allow_html=True)

# --- 0. 移动端适配 CSS ---
st.markdown("""
    <style>
        /* 1. 隐藏顶部的 Streamlit 汉堡菜单和红线 (可选，让 App 更沉浸) */
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        
        /* 2. 隐藏底部的 "Made with Streamlit" */
        footer {visibility: hidden;}
        
        /* 3. 核心：减少页面边缘留白，手机上不再浪费空间 */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 1rem !important;
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
        }
        
        /* 4. 优化 Metric 指标卡的显示 (防止手机上字体过大换行) */
        [data-testid="stMetricValue"] {
            font-size: 1.5rem !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- 1. 侧边栏配置 ---
with st.sidebar:
    st.header("⚙️ 数据与参数")
    
    # 1. 先初始化 data_source 为 None (防止后面报错)
    data_source = None  
    
    # 2. 获取 URL 参数
    query_params = st.query_params
    auto_url = query_params.get("csv_url", None)
    
    if auto_url:
        st.success("✅ 已自动同步云端数据")
        data_source = auto_url  # 情况 A: 赋值为链接
        if st.button("🔄 刷新数据"):
            st.rerun()
    else:
        # 情况 B: 赋值为上传的文件
        uploaded_file = st.file_uploader("上传 saving.csv", type="csv")
        if uploaded_file:
            data_source = uploaded_file
    
    st.divider()
    st.subheader("📅 职业/生活里程碑")
    
    # 初始化默认里程碑数据
    default_milestones = pd.DataFrame([
        {"日期": datetime(2023, 6, 14).date(), "名称": "公司A"}
        # {"日期": datetime(2024, 1, 1).date(), "名称": "公司B"} # 手动添加第二阶段
    ])
    
    # 修复 TypeError：删除了 placeholder 参数
    ms_df = st.data_editor(
        default_milestones,
        num_rows="dynamic",  # 允许用户点击表格下方的 (+) 自由添加行
        column_config={
            "日期": st.column_config.DateColumn(
                "日期", 
                format="YYYY-MM-DD", 
                required=True,
                help="点击可选择日期"
            ),
            "名称": st.column_config.TextColumn(
                "阶段名称", 
                required=True,
                help="输入该阶段的单位或描述"
            )
        },
        hide_index=True,
        use_container_width=True,
        key="milestone_editor"
    )
    
    # 解析数据：将表格内容转换为程序可读的格式
    milestones = []
    if ms_df is not None and not ms_df.empty:
        # 过滤掉日期或名称为空的无效行
        valid_df = ms_df.dropna(subset=['日期', '名称'])
        for _, row in valid_df.iterrows():
            milestones.append({
                "date": pd.to_datetime(row['日期']), 
                "label": str(row['名称']).strip()
            })
    
    # 按日期排序，确保阶段划分正确
    milestones = sorted(milestones, key=lambda x: x['date'])
    
    # 基础参数兼容
    sd_input = st.date_input("记账起始日", datetime(2023, 2, 25))
    start_dt = pd.Timestamp(sd_input)
    # job_start_dt 默认取第一个里程碑，若无则取初始值
    job_start_dt = milestones[0]['date'] if milestones else pd.Timestamp(datetime(2023, 6, 14))
    
    
    st.divider()
    st.subheader("🎯 目标与设置")
    target_goal = st.number_input("目标金额 (元)", value=1000000, step=100000)
    velocity_step = st.number_input("进阶步长 (元)", value=100000, step=10000)
    
    st.divider()
    # 隐私模式开关
    privacy_mode = st.checkbox("👁️ 开启隐私模式 (隐藏金额)", value=False, help="隐藏所有资产绝对数值，适合截屏分享")

# --- 2. 辅助函数：隐私脱敏 ---
def fmt_money(val, is_kpi=False):
    """根据隐私模式格式化金额"""
    if privacy_mode:
        return "****"
    if is_kpi:
        return f"¥{val:,.0f}"
    return val

def mask_fig(fig, axis='y'):
    """隐藏图表中的金额轴和提示"""
    if privacy_mode:
        # 隐藏轴刻度
        if axis == 'y':
            fig.update_yaxes(showticklabels=False, title_text="****")
        elif axis == 'x':
            fig.update_xaxes(showticklabels=False, title_text="****")
        
        # 隐藏悬停信息中的数值
        fig.update_traces(hovertemplate="%{x}<br>****") 
        
        # 将文本模板置为空字符串，从而隐藏柱状图或热力图上的数字
        fig.update_traces(texttemplate="")

    # === 🆕 新增：移动端图表布局优化 ===
    fig.update_layout(
        # 1. 减少图表四周的留白
        margin=dict(l=10, r=10, t=30, b=10),
        # 2. 图例放到顶部水平排列，不占用绘图区
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        
    return fig

# --- 3. 核心数据处理 ---
@st.cache_data(ttl=1)
def load_and_process_data(file, start_date_val, job_start_val):
    df = pd.read_csv(file)
    base_date = pd.Timestamp(start_date_val)
    df['Date'] = df['Day'].apply(lambda x: base_date + timedelta(days=float(x)))
    
    # 基础清洗
    df['Bank'] = df['Bank'].fillna(0).astype(float)
    df['Invest'] = df['Invest'].fillna(0).astype(float)
    df['Total_Assets'] = df['Bank'] + df['Invest']
    df['Change'] = df['Total_Assets'].diff().fillna(0)
    df['Notes'] = df['Notes'].fillna('').astype(str)
    
    # --- 【新增】自适应标签解析逻辑 ---
    # A. 自适应分类逻辑
    def adaptive_tagging(row):
        note = str(row['Notes']).strip()
        change = row['Change']
        if change == 0 and not note: return '无变动'
        
        import re
        segments = re.split('[;；]', note)
        valid_cats = []
        for s in segments:
            parts = re.split('[:：]', s)
            cat = parts[0].strip()
            # 排除非财务统计词（可根据普适性需求增删）
            if cat and cat not in ['里程碑', '备注', '备忘', '2025', '2026']:
                valid_cats.append(cat)
        
        # 资产转移检测
        if any(k in note for k in ['理财', '买入', '基金', '转入']) and abs(change) < 10:
            return '资产转移'

        res_tag = valid_cats[0] if valid_cats else "其他"
        prefix = "📈 收入:" if change > 0 else "💸 支出:"
        return f"{prefix}{res_tag}"

    df['Tag'] = df.apply(adaptive_tagging, axis=1)
    
    # B. 动态阶段划分逻辑
    # 动态阶段划分逻辑：名称 + 相对年份
    def assign_stage_dynamic(d):
        current_label = "初始阶段"
        stage_start_date = milestones[0]['date'] if milestones else d
        
        for m in milestones:
            if d >= m['date']:
                current_label = m['label']
                stage_start_date = m['date']
            else:
                break
        
        # 计算在该阶段内是第几年 (1-based)
        years_passed = (d - stage_start_date).days // 365
        return f"{current_label} (第{years_passed + 1}年)"
    
    df['Stage'] = df['Date'].apply(assign_stage_dynamic)
    
    # 月度数据
    df_res = df.set_index('Date')['Total_Assets'].resample('M').last()
    monthly_diff = df_res.diff().fillna(0)
    
    # 季节性数据
    season_df = pd.DataFrame({'Net_Change': monthly_diff})
    season_df['Year'] = season_df.index.year
    season_df['Month'] = season_df.index.month
    season_pivot = season_df.pivot(index='Year', columns='Month', values='Net_Change')
    
    # 为绘图映射中文列名
    df['资产类型:银行'] = df['Bank']
    df['资产类型:投资'] = df['Invest']
    
    return df, monthly_diff, season_pivot

# --- 4. 里程碑速率计算 ---
def calculate_milestone_velocity(df, step):
    milestones = []
    start_val = df['Total_Assets'].min()
    current_target = (start_val // step + 1) * step
    last_date = df['Date'].iloc[0]
    sorted_df = df.sort_values('Date')
    
    while current_target <= df['Total_Assets'].max():
        reach_row = sorted_df[sorted_df['Total_Assets'] >= current_target].head(1)
        if not reach_row.empty:
            curr_date = reach_row['Date'].iloc[0]
            days_taken = (curr_date - last_date).days
            if days_taken < 1: days_taken = 1
            
            # 隐私模式下隐藏具体里程碑金额
            m_label = "****" if privacy_mode else f"{int(current_target/10000)}w"
            
            milestones.append({
                "里程碑": m_label,
                "所用天数": days_taken,
                "达成日期": curr_date.strftime("%Y-%m-%d")
            })
            last_date = curr_date
            current_target += step
        else:
            break
    return pd.DataFrame(milestones)

# --- 5. 主程序 ---
if data_source:    # ✅ 改成 data_source (这个变量无论哪种情况都有值)
    df, monthly_diff, season_pivot = load_and_process_data(data_source, start_dt, job_start_dt)
    
    # 标题隐私处理
    title_goal = "****" if privacy_mode else f"¥{target_goal:,.0f}"
    st.title(f"📊 个人财务看板 (目标: {title_goal})")
    
    # KPIs
    curr_total = df['Total_Assets'].iloc[-1]
    curr_stage = df['Stage'].iloc[-1]
    last_change = df['Change'].iloc[-1]
    
    stage_df = df[df['Stage'] == curr_stage]
    if len(stage_df) > 1:
        stage_growth = stage_df['Total_Assets'].iloc[-1] - stage_df['Total_Assets'].iloc[0]
        stage_days = (stage_df['Date'].max() - stage_df['Date'].min()).days
        stage_velocity = stage_growth / stage_days if stage_days > 0 else 0
    else:
        stage_velocity = 0
    
    # 格式化 KPI
    kpi_total = fmt_money(curr_total, True)
    kpi_change = "****" if privacy_mode else f"{last_change:+,.0f}"
    kpi_velocity = "****" if privacy_mode else f"¥{stage_velocity:.2f}"


    # 计算最近一年的增长速率 (更加灵敏反映当前状态)
    one_year_ago = df['Date'].iloc[-1] - timedelta(days=365)
    recent_year_df = df[df['Date'] >= one_year_ago]
    
    if len(recent_year_df) > 1:
        recent_growth = recent_year_df['Total_Assets'].iloc[-1] - recent_year_df['Total_Assets'].iloc[0]
        recent_days = (recent_year_df['Date'].max() - recent_year_df['Date'].min()).days
        # 计算近一年日均增速
        display_velocity = recent_growth / recent_days if recent_days > 0 else 0
    else:
        display_velocity = 0

    # 在 KPI 栏位显示
    # c1, c2, c3, c4 = st.columns(4)
    # c1.metric("当前总资产", kpi_total, f"最新: {kpi_change}")
    # c2.metric("当前阶段", curr_stage)
    # c3.metric("近365日均积累", f"¥{display_velocity:,.1f} /天")
    # c4.metric("现金占比 (Bank)", f"{(df['Bank'].iloc[-1]/curr_total)*100:.1f}%")

    # ✅ 移动端优化写法：分成两行
    col_row1 = st.columns(2)
    col_row1[0].metric("当前总资产", kpi_total, f"最新: {kpi_change}")
    col_row1[1].metric("当前阶段", curr_stage)
    
    col_row2 = st.columns(2)
    col_row2[0].metric("近365日均积累", f"¥{display_velocity:,.1f} /天")
    col_row2[1].metric("现金占比", f"{(df['Bank'].iloc[-1]/curr_total)*100:.1f}%")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📈 趋势与月盈亏", "⏱️ 进阶速率", "💰 收支与分类", "🏆 预测与热力图"])

    with tab1:
        # 1. 资产趋势图
        st.subheader("📈 资产演变趋势")
        fig_trend = px.area(df, x='Date', y=['资产类型:银行', '资产类型:投资'], 
                             color_discrete_map={"资产类型:银行": "#7fb3d5", "资产类型:投资": "#5b5ea6"},
                             labels={"value": "金额 (元)", "Date": "日期", "variable": "资产类型"})
        
        # 辅助线 (入职) - 使用 add_shape 避开 Pandas Timestamp Bug
        # 遍历所有里程碑，动态添加辅助线
        for m in milestones:
            if m['date'] >= df['Date'].min():
                # 添加垂直虚线
                fig_trend.add_vline(x=m['date'].timestamp() * 1000, 
                                   line_dash="dash", line_color="orange", opacity=0.7)
                # 添加文字标注
                fig_trend.add_annotation(x=m['date'], y=1, yref="paper", text=m['label'], 
                                         showarrow=False, font=dict(color="orange"), 
                                         textangle=-90, xanchor="left", yanchor="top")
        
        # 隐私遮罩 (Y轴是金额)
        mask_fig(fig_trend, axis='y')
        st.plotly_chart(fig_trend, use_container_width=True)
        
        st.divider()
        
        # 2. 月度盈亏图
        st.subheader("🌔 月度净盈亏")
        m_data = monthly_diff.reset_index()
        m_data.columns = ['月份', '金额']
        fig_monthly = px.bar(m_data, x='月份', y='金额', color='金额',
                              labels={"金额": "净盈亏 (元)", "月份": "时间"},
                              color_continuous_scale='RdYlGn')
        
        # 隐私遮罩 (Y轴是金额)
        mask_fig(fig_monthly, axis='y')
        if privacy_mode: fig_monthly.update_coloraxes(showscale=False)
            
        st.plotly_chart(fig_monthly, use_container_width=True)

    with tab2:
        step_label = "****" if privacy_mode else f"{int(velocity_step/10000)}w"
        st.subheader(f"⏱️ 财富进阶速率 (步长: {step_label})")
        v_df = calculate_milestone_velocity(df, velocity_step)
        
        if not v_df.empty:
            fig_v = px.bar(v_df, x='里程碑', y='所用天数', text='所用天数',
                           hover_data=['达成日期'],
                           labels={"所用天数": "耗时 (天)", "里程碑": "资产里程碑"},
                           color='所用天数', color_continuous_scale='RdYlBu_r')
            st.plotly_chart(fig_v, use_container_width=True)
        else:
            st.info("数据跨度不足。")
            
        st.divider()
        st.subheader("🗓️ 年度平均存钱速率")

        # 1. 按年份计算增长额与天数
        df['Year'] = df['Date'].dt.year
        yearly_summary = []
        
        for year, group in df.groupby('Year'):
            if len(group) > 1:
                # 计算该年份内的首尾差额
                growth = group['Total_Assets'].iloc[-1] - group['Total_Assets'].iloc[0]
                # 计算该年份内记录的天数
                days = (group['Date'].max() - group['Date'].min()).days
                if days > 0:
                    velocity = growth / days
                    yearly_summary.append({
                        "年份": str(year), 
                        "日均增长": round(velocity, 1),
                        "年累计增长": growth
                    })
        
        y_df = pd.DataFrame(yearly_summary)

        if not y_df.empty:
            # 2. 绘制年度速率对比图
            fig_year = px.bar(
                y_df, x='年份', y='日均增长', text='日均增长',
                labels={"日均增长": "日均增长 (元/天)", "年份": "年份"},
                color='日均增长', color_continuous_scale='GnBu'
            )
            fig_year.update_xaxes(dtick=1)            
            
            # 隐私模式遮罩
            if privacy_mode:
                fig_year.update_traces(texttemplate="****")
                fig_year.update_yaxes(showticklabels=False, title_text="****")
                fig_year.update_coloraxes(showscale=False)
            else:
                fig_year.update_traces(textposition='outside')
            
            st.plotly_chart(fig_year, use_container_width=True)
            
            # 3. 补充说明文字
            st.caption("注：日均增长 = (当年最后一天总资产 - 当年第一天总资产) / 当年记录天数")
        else:
            st.info("数据年份不足，无法生成年度对比。")

    with tab3:
        st.subheader("📊 账目分类统计")
        # 1. 先计算完整的统计数据
        full_stats = df[df['Change'] != 0].groupby('Tag')['Change'].sum().reset_index()
        
        # 2. 分别提取支出前十（Change 最小的 10 个）和 收入前十（Change 最大的 10 个）
        top_exp_tags = full_stats.nsmallest(10, 'Change')
        top_inc_tags = full_stats.nlargest(10, 'Change')
        
        # 3. 合并并去重（防止分类太少导致重复），然后按金额排序
        tag_stats = pd.concat([top_exp_tags, top_inc_tags]).drop_duplicates().sort_values('Change')
        
        # 4. 绘图（沿用之前的 height 设置）
        fig_tag = px.bar(
            tag_stats, 
            x='Change', 
            y='Tag', 
            orientation='h', 
            labels={"Change": "净额 (元)", "Tag": "分类"},
            color='Change', 
            # 使用典型的发散色谱：RdBu (红-白-蓝) 或 PiYG (粉-白-绿)
            # 蓝色/绿色代表正向收入，红色/粉色代表负向支出
            color_continuous_scale='RdBu', 
            # 核心设置：强制 0 为颜色的中点（白色）
            color_continuous_midpoint=0, 
            height=600
        )
        
       
        # 隐私遮罩 (X轴是金额)
        mask_fig(fig_tag, axis='x')
        if privacy_mode: fig_tag.update_coloraxes(showscale=False)
            
        st.plotly_chart(fig_tag, use_container_width=True)
        
        st.divider()
        c_left, c_right = st.columns(2)
        
        # 表格隐私处理函数
        def display_df_masked(in_df):
            out_df = in_df.copy()
            if privacy_mode:
                out_df['Change'] = "****"
            else:
                out_df['Change'] = out_df['Change'].apply(lambda x: f"{x:+,.0f}")
            return out_df

        with c_left:
            st.subheader("📈 收入 Top 10")
            top_inc = df[df['Change'] > 0].nlargest(10, 'Change')[['Date', 'Change', 'Notes', 'Tag']]
            top_inc['Date'] = top_inc['Date'].dt.strftime('%Y-%m-%d')
            st.dataframe(display_df_masked(top_inc), use_container_width=True)
            
        with c_right:
            st.subheader("💸 支出 Top 10")
            top_exp = df[df['Change'] < 0].nsmallest(10, 'Change')[['Date', 'Change', 'Notes', 'Tag']]
            top_exp['Date'] = top_exp['Date'].dt.strftime('%Y-%m-%d')
            st.dataframe(display_df_masked(top_exp), use_container_width=True)

    with tab4:
        st.subheader(f"🚀 基于【{curr_stage}】的里程碑预测")
        
        if stage_velocity > 0:
            remaining = target_goal - curr_total
            if remaining > 0:
                days_needed = remaining / stage_velocity
                pred_date = (datetime.now() + timedelta(days=days_needed)).date()
                
                # 预测文案隐私处理
                display_goal = "****" if privacy_mode else f"¥{target_goal:,.0f}"
                display_rem = "****" if privacy_mode else f"¥{remaining:,.0f}"
                display_vel = "****" if privacy_mode else f"¥{stage_velocity:.2f}"
                
                st.success(f"🎯 距离目标 **{display_goal}** 还差 **{display_rem}**")
                st.write(f"当前阶段 (**{curr_stage}**) 平均增速：**{display_vel} / 天**")
                st.info(f"📅 预计达成日期：**{pred_date}** (约需 {int(days_needed)} 天)")
            else:
                st.balloons()
                st.success("🎉 恭喜！您已达成目标！")
        else:
            st.warning("⚠️ 当前阶段暂无正向增长数据。")
            
        st.divider()
        st.subheader("🔥 季节性热力图 (单位: k)")
        if not season_pivot.empty:
            # 隐私模式下隐藏具体数值
            text_auto_val = False if privacy_mode else '.1f'
            
            fig_heat = px.imshow(season_pivot.fillna(0)/1000, 
                                 text_auto=text_auto_val, 
                                 labels={"color": "净值 (k)", "x": "月份", "y": "年份"},
                                 color_continuous_scale='RdYlGn', aspect="auto")
            
            # 【核心修改】强制 Y 轴（年份）刻度间隔为 1，确保显示整数年份
            fig_heat.update_yaxes(dtick=1)
            fig_heat.update_xaxes(dtick=1)

            # 隐私模式处理
            if privacy_mode:
                fig_heat.update_coloraxes(showscale=False)
                fig_heat.update_traces(hovertemplate="年份: %{y}<br>月份: %{x}<br>****")
                fig_heat.update_traces(texttemplate="")
                
            st.plotly_chart(fig_heat, use_container_width=True)

else:
    st.info("👋 请在侧边栏上传 `saving.csv`。")
    
# --- 6. 底部使用帮助 ---
    st.divider()
    with st.expander("📘 查看使用帮助与记账规范", expanded=False):
        try:
            import os
            # 确保在不同操作系统下都能正确找到文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            help_path = os.path.join(current_dir, "README.md")
            
            with open(help_path, "r", encoding="utf-8") as f:
                st.markdown(f.read())
        except FileNotFoundError:
            st.warning("⚠️ 文件夹中未找到 README.md，请创建该文件。")















