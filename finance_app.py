import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import re
from datetime import datetime, timedelta

# --- 页面配置 ---
st.set_page_config(page_title="Jincheng's 财务看板", layout="wide")

# --- 0. 移动端适配 CSS ---
st.markdown("""
    <style>
        /* 1. 隐藏多余元素 */
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* 2. 核心布局调整：增加呼吸感 */
        .block-container {
            padding-top: 2rem !important;    /* 顶部留出更多空间 */
            padding-bottom: 3rem !important; /* 底部防止被手势条遮挡 */
            padding-left: 1.2rem !important; /* 左侧标准 20px 边距 */
            padding-right: 1.2rem !important;/* 右侧标准 20px 边距 */
        }
        
        /* 3. 优化 Metric 指标卡的显示 */
        [data-testid="stMetricValue"] {
            font-size: 1.4rem !important; /* 稍微调小一点点，防止数值太长换行 */
        }
        
        /* 4. 优化 Tabs 的点击区域 */
        button[data-baseweb="tab"] {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- 1. 布局定义 ---
# 定义顶部占位符（用于稍后显示核心KPI）
kpi_placeholder = st.container()
# 定义 5 个标签页，把“设置”放在最后
tab5, tab1, tab2, tab3, tab4 = st.tabs(["⚙️ 设置", "📈 趋势", "⏱️ 速率", "💰 分类", "🏆 预测"])

# =========================================================
#  Tab 5: 设置 (原侧边栏内容) - 优先执行以获取参数
# =========================================================
with tab5:
    st.header("⚙️ 数据与参数设置")
    
    # --- A. 数据源逻辑 ---
    # --- A. 数据源逻辑 (升级版：双通道输入) ---
    st.subheader("1. 数据源配置")
    
    # 1. 尝试获取 App 传来的参数 (如果有，作为默认值填入框内)
    try:
        query_params = st.query_params
    except:
        query_params = st.experimental_get_query_params()
    app_url_param = query_params.get("csv_url", "")
    if isinstance(app_url_param, list): app_url_param = app_url_param[0]

    # 2. 链接输入框 (默认填入 App 参数，但允许你手动修改/粘贴新链接)
    # value=... 只有在脚本第一次运行时生效，后续你的修改会被 Streamlit 记住
    csv_link_input = st.text_input(
        "🌐 云端链接 (Google Sheet CSV)", 
        value=app_url_param or "",
        placeholder="https://docs.google.com/.../pub?output=csv",
        help="App 自动同步的链接显示在这里，你也可以手动修改它。"
    )

    # 3. 本地文件上传框 (始终显示)
    uploaded_file = st.file_uploader("📂 或上传本地 CSV 文件 (优先级最高)", type="csv")

    # 4. 决策逻辑：决定到底用哪个数据
    data_source = None
    
    if uploaded_file:
        # 优先级 1：如果你传了本地文件，强制使用本地文件
        st.info("✅ 模式：正在使用本地上传文件")
        data_source = uploaded_file
    elif csv_link_input:
        # 优先级 2：没传文件，但框里有链接，使用链接
        # 简单校验一下是不是网址
        if csv_link_input.startswith("http"):
            st.success("☁️ 模式：正在使用云端链接")
            data_source = csv_link_input
            # 加个刷新按钮，因为云端数据可能会变
            if st.button("🔄 立即刷新云端数据", use_container_width=True):
                st.rerun()
        else:
            st.warning("⚠️ 链接格式似乎不正确，请以 http 开头")
    else:
        st.warning("👋 请在上方输入链接或上传文件")

    st.divider()

    # --- B. 里程碑设置 (支持自定义标签) ---
    st.subheader("2. 职业/生活里程碑")
    
    # 🎯 核心修改：尝试获取 App 传来的 label 参数
    app_label_param = query_params.get("label", "")
    if isinstance(app_label_param, list): app_label_param = app_label_param[0]
    
    # 如果有 App 传来的值 (SICCAS)，就用它；否则默认用 "公司A"
    default_company_name = app_label_param if app_label_param else "公司A"
    
    default_milestones = pd.DataFrame([
        {"日期": datetime(2023, 6, 14).date(), "名称": default_company_name}
    ])
    
    ms_df = st.data_editor(
        default_milestones,
        num_rows="dynamic",
        column_config={
            "日期": st.column_config.DateColumn("日期", format="YYYY-MM-DD", required=True),
            "名称": st.column_config.TextColumn("阶段名称", required=True)
        },
        hide_index=True,
        use_container_width=True,
        key="milestone_editor"
    )
    
    milestones = []
    if ms_df is not None and not ms_df.empty:
        valid_df = ms_df.dropna(subset=['日期', '名称'])
        for _, row in valid_df.iterrows():
            milestones.append({
                "date": pd.to_datetime(row['日期']), 
                "label": str(row['名称']).strip()
            })
    milestones = sorted(milestones, key=lambda x: x['date'])

    st.divider()

    # --- C. 目标与显示设置 (原版逻辑) ---
    st.subheader("3. 目标与显示")
    # 使用列布局节省空间
    c_set1, c_set2 = st.columns(2)
    with c_set1:
        sd_input = st.date_input("记账起始日", datetime(2023, 2, 25))
        target_goal = st.number_input("目标金额 (元)", value=1000000, step=100000)
    with c_set2:
        velocity_step = st.number_input("进阶步长 (元)", value=100000, step=10000)
        privacy_mode = st.toggle("👁️ 隐私模式 (隐藏金额)", value=False)

    # 整理全局参数
    start_dt = pd.Timestamp(sd_input)
    job_start_dt = milestones[0]['date'] if milestones else pd.Timestamp(datetime(2023, 6, 14))


# --- 辅助函数：完全保留原版逻辑 ---
def fmt_money(val, is_kpi=False):
    """根据隐私模式格式化金额"""
    if privacy_mode:
        return "****"
    if is_kpi:
        return f"¥{val:,.0f}"
    return val

def mask_fig(fig, axis='y'):
    """
    1. 隐藏图表中的金额轴和提示，适配隐私模式
    2. [核心修改] 适配移动端：锁定坐标轴，防止手指误触导致无法滚动页面
    """
    # --- A. 移动端核心适配 ---
    # 1. 调整边距和图例 (保留之前的优化)
    fig.update_layout(
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        # 2. 禁止鼠标/手指拖动图表 (dragmode=False)
        dragmode=False 
    )
    
    # 3. 关键：强制锁定 X 轴和 Y 轴，让触摸事件“穿透”图表传给页面滚动
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)

    # --- B. 隐私模式逻辑 (保留原版) ---
    if privacy_mode:
        if axis == 'y':
            fig.update_yaxes(showticklabels=False, title_text="****")
        elif axis == 'x':
            fig.update_xaxes(showticklabels=False, title_text="****")
        
        fig.update_traces(hovertemplate="%{x}<br>****") 
        fig.update_traces(texttemplate="")
        
    return fig

# --- 核心数据处理：完全保留原版算法 ---
@st.cache_data(ttl=1)
def load_and_process_data(file, start_date_val, job_start_val):
    # 支持 URL 读取
    df = pd.read_csv(file)
    base_date = pd.Timestamp(start_date_val)
    # 还原真实日期
    df['Date'] = df['Day'].apply(lambda x: base_date + timedelta(days=float(x)))
    
    # 基础清洗
    df['Bank'] = df['Bank'].fillna(0).astype(float)
    df['Invest'] = df['Invest'].fillna(0).astype(float)
    df['Total_Assets'] = df['Bank'] + df['Invest']
    df['Change'] = df['Total_Assets'].diff().fillna(0)
    df['Notes'] = df['Notes'].fillna('').astype(str)
    
    # --- 自适应标签解析逻辑 (原版) ---
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
            # 排除非财务统计词
            if cat and cat not in ['里程碑', '备注', '备忘', '2025', '2026']:
                valid_cats.append(cat)
        
        # 资产转移检测
        if any(k in note for k in ['理财', '买入', '基金', '转入']) and abs(change) < 10:
            return '资产转移'

        res_tag = valid_cats[0] if valid_cats else "其他"
        prefix = "📈 收入:" if change > 0 else "💸 支出:"
        return f"{prefix}{res_tag}"

    df['Tag'] = df.apply(adaptive_tagging, axis=1)
    
    # --- 动态阶段划分逻辑 (原版) ---
    def assign_stage_dynamic(d):
        current_label = "初始阶段"
        stage_start_date = milestones[0]['date'] if milestones else d
        
        for m in milestones:
            if d >= m['date']:
                current_label = m['label']
                stage_start_date = m['date']
            else:
                break
        
        # 计算在该阶段内是第几年
        years_passed = (d - stage_start_date).days // 365
        return f"{current_label} (第{years_passed + 1}年)"
    
    df['Stage'] = df['Date'].apply(assign_stage_dynamic)
    
    # 月度数据
    df_res = df.set_index('Date')['Total_Assets'].resample('ME').last()
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

# --- 速率计算逻辑 (原版) ---
def calculate_milestone_velocity(df, step):
    milestones_res = []
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
            
            m_label = "****" if privacy_mode else f"{int(current_target/10000)}w"
            
            milestones_res.append({
                "里程碑": m_label,
                "所用天数": days_taken,
                "达成日期": curr_date.strftime("%Y-%m-%d")
            })
            last_date = curr_date
            current_target += step
        else:
            break
    return pd.DataFrame(milestones_res)

# =========================================================
#  主程序执行逻辑
# =========================================================
if data_source:
    df, monthly_diff, season_pivot = load_and_process_data(data_source, start_dt, job_start_dt)
    
    # --- 1. 顶部 KPI 看板 (填充占位符) ---
    with kpi_placeholder:
        title_goal = "****" if privacy_mode else f"¥{target_goal:,.0f}"
        st.subheader(f"📊 个人财务看板 (目标: {title_goal})")
        
        # 计算核心指标
        curr_total = df['Total_Assets'].iloc[-1]
        curr_stage = df['Stage'].iloc[-1]
        last_change = df['Change'].iloc[-1]
        
        # 近一年增速计算
        one_year_ago = df['Date'].iloc[-1] - timedelta(days=365)
        recent_year_df = df[df['Date'] >= one_year_ago]
        if len(recent_year_df) > 1:
            recent_growth = recent_year_df['Total_Assets'].iloc[-1] - recent_year_df['Total_Assets'].iloc[0]
            recent_days = (recent_year_df['Date'].max() - recent_year_df['Date'].min()).days
            display_velocity = recent_growth / recent_days if recent_days > 0 else 0
        else:
            display_velocity = 0

        kpi_total = fmt_money(curr_total, True)
        kpi_change = "****" if privacy_mode else f"{last_change:+,.0f}"

        # 移动端 2x2 布局，但保留原版所有数据精度
        row1 = st.columns(2)
        row1[0].metric("当前总资产", kpi_total, f"最新: {kpi_change}")
        row1[1].metric("当前阶段", curr_stage)
        
        if privacy_mode:
            vel_str = "**** /天"
        else:
            vel_str = f"¥{display_velocity:,.1f} /天"
            
        row2 = st.columns(2)
        row2[0].metric("近365日均积累", vel_str)
        row2[1].metric("现金占比", f"{(df['Bank'].iloc[-1]/curr_total)*100:.1f}%")
        st.divider()

    # --- 2. Tab 1: 趋势与月盈亏 (恢复原版图表配置) ---
    with tab1:
        st.subheader("📈 资产演变趋势")
        # 恢复原版配色和设置
        fig_trend = px.area(df, x='Date', y=['资产类型:银行', '资产类型:投资'], 
                             color_discrete_map={"资产类型:银行": "#7fb3d5", "资产类型:投资": "#5b5ea6"},
                             labels={"value": "金额 (元)", "Date": "日期", "variable": "资产类型"})
        
        # 恢复辅助线和文字标注
        for m in milestones:
            if m['date'] >= df['Date'].min():
                fig_trend.add_vline(x=m['date'].timestamp() * 1000, 
                                   line_dash="dash", line_color="orange", opacity=0.7)
                fig_trend.add_annotation(x=m['date'], y=1, yref="paper", text=m['label'], 
                                         showarrow=False, font=dict(color="orange"), 
                                         textangle=-90, xanchor="left", yanchor="top")
        
        mask_fig(fig_trend, axis='y')
        st.plotly_chart(fig_trend, use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        
        st.subheader("🌔 月度净盈亏")
        m_data = monthly_diff.reset_index()
        m_data.columns = ['月份', '金额']
        # 恢复原版色阶
        fig_monthly = px.bar(m_data, x='月份', y='金额', color='金额',
                              labels={"金额": "净盈亏 (元)", "月份": "时间"},
                              color_continuous_scale='RdYlGn')
        
        mask_fig(fig_monthly, axis='y')
        if privacy_mode: fig_monthly.update_coloraxes(showscale=False)
        st.plotly_chart(fig_monthly, use_container_width=True, config={'displayModeBar': False})

    # --- 3. Tab 2: 进阶速率 (恢复原版) ---
    with tab2:
        step_label = "****" if privacy_mode else f"{int(velocity_step/10000)}w"
        st.subheader(f"⏱️ 财富进阶速率 (步长: {step_label})")
        
        v_df = calculate_milestone_velocity(df, velocity_step)
        if not v_df.empty:
            fig_v = px.bar(v_df, x='里程碑', y='所用天数', text='所用天数',
                           hover_data=['达成日期'],
                           labels={"所用天数": "耗时 (天)", "里程碑": "资产里程碑"},
                           color='所用天数', color_continuous_scale='RdYlBu_r')
            mask_fig(fig_v, axis='y')
            st.plotly_chart(fig_v, use_container_width=True, config={'displayModeBar': False})            
        else:
            st.info("数据跨度不足。")        
            
        st.divider()
        st.subheader("🗓️ 年度平均存钱速率")

        df['Year'] = df['Date'].dt.year
        yearly_summary = []
        for year, group in df.groupby('Year'):
            if len(group) > 1:
                growth = group['Total_Assets'].iloc[-1] - group['Total_Assets'].iloc[0]
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
            fig_year = px.bar(
                y_df, x='年份', y='日均增长', text='日均增长',
                labels={"日均增长": "日均增长 (元/天)", "年份": "年份"},
                color='日均增长', color_continuous_scale='GnBu'
            )
            mask_fig(fig_year, axis='y')
            fig_year.update_xaxes(dtick=1) # 强制显示整数年份
            
            if privacy_mode:
                fig_year.update_traces(texttemplate="****")
                fig_year.update_yaxes(showticklabels=False, title_text="****")
                fig_year.update_coloraxes(showscale=False)
            else:
                fig_year.update_traces(textposition='outside')
            
            st.plotly_chart(fig_year, use_container_width=True, config={'displayModeBar': False})
            # st.caption("注：日均增长 = (当年最后一天总资产 - 当年第一天总资产) / 当年记录天数")

    # --- 4. Tab 3: 收支与分类 (恢复被删减的数据表) ---
    with tab3:
        st.subheader("📊 账目分类统计")
        full_stats = df[df['Change'] != 0].groupby('Tag')['Change'].sum().reset_index()
        
        top_exp_tags = full_stats.nsmallest(10, 'Change')
        top_inc_tags = full_stats.nlargest(10, 'Change')
        tag_stats = pd.concat([top_exp_tags, top_inc_tags]).drop_duplicates().sort_values('Change')
        
        # 恢复原版 Bar chart 设置
        fig_tag = px.bar(
            tag_stats, 
            x='Change', 
            y='Tag', 
            orientation='h', 
            labels={"Change": "净额 (元)", "Tag": "分类"},
            color='Change', 
            color_continuous_scale='RdBu', 
            color_continuous_midpoint=0, 
            height=600
        )
        
        mask_fig(fig_tag, axis='x')
        if privacy_mode: fig_tag.update_coloraxes(showscale=False)
        st.plotly_chart(fig_tag, use_container_width=True, config={'displayModeBar': False})
        
        st.divider()
        
        # === 重点恢复：原版的详细数据表 ===
        c_left, c_right = st.columns(2)
        
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

    # --- 5. Tab 4: 预测与热力图 (恢复原版细节) ---
    with tab4:
        curr_stage_name = df['Stage'].iloc[-1]
        st.subheader(f"🚀 基于【{curr_stage_name}】的里程碑预测")
        
        # 计算当前阶段速率 (原版逻辑)
        stage_df = df[df['Stage'] == curr_stage_name]
        stage_velocity = 0
        if len(stage_df) > 1:
            stage_growth = stage_df['Total_Assets'].iloc[-1] - stage_df['Total_Assets'].iloc[0]
            stage_days = (stage_df['Date'].max() - stage_df['Date'].min()).days
            if stage_days > 0: stage_velocity = stage_growth / stage_days
        
        if stage_velocity > 0:
            remaining = target_goal - curr_total
            if remaining > 0:
                days_needed = remaining / stage_velocity
                pred_date = (datetime.now() + timedelta(days=days_needed)).date()
                
                display_goal = "****" if privacy_mode else f"¥{target_goal:,.0f}"
                display_rem = "****" if privacy_mode else f"¥{remaining:,.0f}"
                display_vel = "****" if privacy_mode else f"¥{stage_velocity:.2f}"
                
                st.success(f"🎯 距离目标 **{display_goal}** 还差 **{display_rem}**")
                st.write(f"当前阶段 (**{curr_stage_name}**) 平均增速：**{display_vel} / 天**")
                st.info(f"📅 预计达成日期：**{pred_date}** (约需 {int(days_needed)} 天)")
            else:
                st.balloons()
                st.success("🎉 恭喜！您已达成目标！")
        else:
            st.warning("⚠️ 当前阶段暂无正向增长数据，无法预测。")
            
        st.divider()
        st.subheader("🔥 季节性热力图 (单位: k)")
        if not season_pivot.empty:
            text_auto_val = False if privacy_mode else '.1f'
            
            fig_heat = px.imshow(season_pivot.fillna(0)/1000, 
                                 text_auto=text_auto_val, 
                                 labels={"color": "净值 (k)", "x": "月份", "y": "年份"},
                                 color_continuous_scale='RdYlGn', aspect="auto")
            mask_fig(fig_heat, axis='y')
            # 恢复原版：强制显示整数年份
            fig_heat.update_yaxes(dtick=1)
            fig_heat.update_xaxes(dtick=1)

            if privacy_mode:
                fig_heat.update_coloraxes(showscale=False)
                fig_heat.update_traces(hovertemplate="年份: %{y}<br>月份: %{x}<br>****")
                fig_heat.update_traces(texttemplate="")
                
            st.plotly_chart(fig_heat, use_container_width=True, config={'displayModeBar': False})

else:
    # 引导页
    with kpi_placeholder:
        st.info("👋 欢迎！请点击下方的 **[⚙️ 设置]** 标签页来绑定数据。")













