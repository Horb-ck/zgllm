// --- 统一配置区 ---
// 将 AppConfig 的定义移到一个函数内部，确保它在需要时才被初始化。
function getAppConfig() {
    // 尝试从后端注入的 window.PAGE_DATA 对象中获取配置。
    // 如果获取不到（例如，直接打开HTML文件时），则使用预设的默认值。
    const config = {
        API_BASE_URL: '/kg',
        className: (window.PAGE_DATA && window.PAGE_DATA.courseName) ? window.PAGE_DATA.courseName : '程序设计实践',
        studentId: (window.PAGE_DATA && window.PAGE_DATA.studentId) ? window.PAGE_DATA.studentId : '2002'
    };
    // 这个日志现在会在正确的时间点打印正确的值
    console.log("AppConfig initialized with:", config);
    return config;
}

const chartDomId = '4ed221bd03f84e8b9227cdd3d973b8bc';
var chart_4ed221bd03f84e8b9227cdd3d973b8bc = echarts.init(
    document.getElementById(chartDomId), 'light', { renderer: 'canvas' });
var option_4ed221bd03f84e8b9227cdd3d973b8bc = {
    "animation": true,
    "animationThreshold": 2000,
    "animationDuration": 1000,
    "animationEasing": "cubicOut",
    "animationDelay": 0,
    "animationDurationUpdate": 300,
    "animationEasingUpdate": "cubicOut",
    "animationDelayUpdate": 0,
    "aria": {
        "enabled": false
    },
    "series": [
        {
            "type": "graph",
            "layout": "force",
            "zoom": 0.5,
            "scaleLimit": {
                "min": 0.2,
                "max": 3
            },
            "symbolSize": 10,
            "circular": {
                "rotateLabel": false
            },
            "force": {
                "repulsion": 2500,
                "edgeLength": 50
            },
            "label": {
                "show": true,
                "margin": 8,
                "valueAnimation": false
            },
            "lineStyle": {
                "show": true,
                "width": 2,
                "opacity": 0.5,
                "curveness": 0,
                "type": "solid",
                "color": "#4b565b"
            },
            "roam": true,
            "draggable": true,
            "focusNodeAdjacency": true,
            "data": [],
            "categories": [],
            "edgeLabel": {
                "show": false,
                "margin": 8,
                "valueAnimation": false
            },
            "edgeSymbol": [
                "circle",
                "arrow"
            ],
            "edgeSymbolSize": [
                2,
                10
            ],
            "links": []
        }
    ],
    "legend": [
        {
            "data": [],
            "selected": {},
            "show": false,
            "padding": 5,
            "itemGap": 10,
            "itemWidth": 25,
            "itemHeight": 14,
            "backgroundColor": "transparent",
            "borderColor": "#ccc",
            "borderRadius": 0,
            "pageButtonItemGap": 5,
            "pageButtonPosition": "end",
            "pageFormatter": "{current}/{total}",
            "pageIconColor": "#2f4554",
            "pageIconInactiveColor": "#aaa",
            "pageIconSize": 15,
            "animationDurationUpdate": 800,
            "selector": false,
            "selectorPosition": "auto",
            "selectorItemGap": 7,
            "selectorButtonGap": 10
        }
    ],
    "tooltip": {
        "show": true,
        "trigger": "item",
        "triggerOn": "mousemove|click",
        "axisPointer": {
            "type": "line"
        },
        "showContent": true,
        "alwaysShowContent": false,
        "showDelay": 0,
        "hideDelay": 100,
        "enterable": false,
        "confine": false,
        "appendToBody": false,
        "transitionDuration": 0.4,
        "formatter": "{b}",
        "textStyle": {
            "fontSize": 14
        },
        "borderWidth": 0,
        "padding": 5,
        "order": "seriesAsc"
    },
    "title": [
        {
            "show": false,
            "text": "\u5b9a\u91cf\u5de5\u7a0b\u8bbe\u8ba1\u77e5\u8bc6\u56fe\u8c31",
            "target": "blank",
            "subtarget": "blank",
            "padding": 5,
            "itemGap": 10,
            "textAlign": "auto",
            "textVerticalAlign": "auto",
            "triggerEvent": false
        }
    ],
    "toolbox": {
        "show": false,
        "orient": "horizontal",
        "itemSize": 15,
        "itemGap": 10,
        "left": "80%",
        "feature": {
            "mark": {
                "show": true
            },
            "restore": {
                "show": true
            },
            "saveAsImage": {
                "show": true
            }
        }
    }
};
var rawData = { nodes: [], links: [], categories: [] };
// 用于恢复默认图谱的数据快照
var defaultGraph = { nodes: [], links: [], categories: [] };
// 标记当前是否已切换为生成后的图谱
var isGeneratedGraph = false;

// 从服务器加载初始图谱数据并渲染
function loadAndRenderGraph() {
    // ✨ 关键修改点：在函数执行时才调用 getAppConfig() 获取配置
    const AppConfig = getAppConfig();

    const myChart = chart_4ed221bd03f84e8b9227cdd3d973b8bc;
    const requestUrl = `${AppConfig.API_BASE_URL}/get_all_kg_jsons?class_name=${encodeURIComponent(AppConfig.className)}`;

    console.log(`正在从 ${requestUrl} 加载数据...`);
    myChart.showLoading();

    fetch(requestUrl)
        .then(response => {
            if (!response.ok) {
                return response.text().then(text => {
                    throw new Error(`网络请求失败: ${response.status} ${response.statusText}. 响应内容: ${text}`);
                });
            }
            return response.json();
        })
        .then(apiData => {
            console.log("从服务器收到的原始数据:", apiData);
            let graphData;

            if (apiData && Array.isArray(apiData.data) && apiData.data.length > 0 && apiData.data[0] && apiData.data[0].kg) {
                graphData = apiData.data[0].kg;
            }
            else if (apiData && Array.isArray(apiData.files) && apiData.files.length > 0 && apiData.files[0] && apiData.files[0].kg) {
                graphData = apiData.files[0].kg;
            }
            else if (apiData && Array.isArray(apiData.nodes) && Array.isArray(apiData.links)) {
                graphData = apiData;
            }
            else if (apiData && Array.isArray(apiData.data) && Array.isArray(apiData.links)) {
                graphData = { nodes: apiData.data, links: apiData.links, categories: apiData.categories };
            }
            else {
                throw new Error('API返回的数据格式无法识别。');
            }

            if (graphData && !graphData.nodes && graphData.data) {
                graphData.nodes = graphData.data;
            }

            if (!graphData || !Array.isArray(graphData.nodes) || !Array.isArray(graphData.links)) {
                console.error("验证失败！最终的graphData对象:", graphData);
                throw new Error('解析后的图谱数据(graphData)无效，缺少nodes或links数组。');
            }

            rawData.nodes = graphData.nodes || [];
            rawData.links = graphData.links || [];

            if (graphData.categories && Array.isArray(graphData.categories)) {
                rawData.categories = graphData.categories;
            } else {
                rawData.categories = [...new Set(rawData.nodes.map(node => node.category).filter(Boolean))]
                    .map(name => ({ name }));
            }

            const className = AppConfig.className;
            option_4ed221bd03f84e8b9227cdd3d973b8bc.title[0].text = `${className} (学号：${AppConfig.studentId})`;
            option_4ed221bd03f84e8b9227cdd3d973b8bc.series[0].data = rawData.nodes;
            option_4ed221bd03f84e8b9227cdd3d973b8bc.series[0].links = rawData.links;
            option_4ed221bd03f84e8b9227cdd3d973b8bc.series[0].categories = rawData.categories;
            option_4ed221bd03f84e8b9227cdd3d973b8bc.legend[0].data = rawData.categories.map(c => c.name);

            myChart.setOption(option_4ed221bd03f84e8b9227cdd3d973b8bc, true);
            myChart.resize(); // 初次渲染时立即自适应容器
            setTimeout(function () {
                myChart.resize(); // force 布局稳定后再触发一次，避免首屏溢出
            }, 300);
            myChart.hideLoading();

            console.log(`成功加载并渲染课程 “${className}” (学生：${AppConfig.studentId}) 的知识图谱。`);
            // 缓存默认图谱用于返回
            defaultGraph = {
                nodes: JSON.parse(JSON.stringify(rawData.nodes)),
                links: JSON.parse(JSON.stringify(rawData.links)),
                categories: JSON.parse(JSON.stringify(rawData.categories))
            };
            isGeneratedGraph = false;
            toggleBackButton(false);

            if (typeof fetchAndApplyNodeStatuses === 'function') {
                // 在调用时再次获取正确的AppConfig，或直接传递
                fetchAndApplyNodeStatuses(AppConfig);
            } else {
                console.error("错误：fetchAndApplyNodeStatuses 函数未定义！");
            }
        })
        .catch(error => {
            myChart.hideLoading();
            console.error('加载知识图谱数据时出错:', error);
            const chartDom = document.getElementById(chartDomId);
            if (chartDom) {
                chartDom.innerHTML = `<div style="text-align: center; padding: 50px; color: red;"><h2>加载失败</h2><p>${error.message}</p><p>请检查API服务器(:7000)是否运行正常，或按F12在控制台查看详情。</p></div>`;
            }
        });
}

// 监听 DOMContentLoaded 事件，确保整个页面（包括注入的脚本）都加载完毕再执行。
document.addEventListener('DOMContentLoaded', function () {
    loadAndRenderGraph();
});

window.addEventListener('resize', function () {
    chart_4ed221bd03f84e8b9227cdd3d973b8bc.resize();
});
// 图表操作相关变量
var myChart = null;          // 图表实例
// rawData 已被移到第一个 <script> 块中
var currentState = {         // 当前状态
    mode: 'full',            // 显示模式：'full'=完整图谱, 'focus'=聚焦模式
    focusedNode: null,       // 当前聚焦的节点名称
    highlightedNode: null    // 当前高亮的节点名称
};
var categoriesCache = [];    // 用于缓存分类数据，避免重复获取

// DOM元素
var modal = document.getElementById("nodeModal");
    var modalTitle = document.getElementById("modalTitle");
    var modalBody = document.getElementById("modalBody");
    var closeBtn = document.getElementsByClassName("close")[0];
var searchInput, searchBtn, searchResults, reset; // Added reset here as it's globally used in createSearchBox
var debugPanel = document.getElementById("debugPanel");

// 调试辅助函数
var isDebug = false; // 是否启用调试

function debugLog(message) {
    if (!isDebug) return;

    var time = new Date().toLocaleTimeString();
    var logItem = document.createElement('div');
    logItem.innerHTML = `<span style="color:#aaa">[${time}]</span> ${message}`;

    if (debugPanel) {
        debugPanel.style.display = 'block';
        debugPanel.appendChild(logItem);
        debugPanel.scrollTop = debugPanel.scrollHeight;

        // 保留最多30条日志
        while (debugPanel.children.length > 30) {
            debugPanel.removeChild(debugPanel.children[0]);
        }
    }

    console.log(`[DEBUG] ${message}`);
}

// 按键监听 - 按D键切换调试模式
document.addEventListener('keydown', function (e) {
    if (e.key === 'D' && e.ctrlKey && e.shiftKey) {
        isDebug = !isDebug;
        debugPanel.style.display = isDebug ? 'block' : 'none';
        if (isDebug) {
            debugLog('调试模式已启用');
            debugLog(`当前状态: ${JSON.stringify(currentState)}`);
        }
    }
});

// 事件绑定
if (closeBtn) { // Check if closeBtn exists before assigning onclick
    closeBtn.onclick = function () {
        modal.style.display = "none";
    }
}

window.onclick = function (event) {
    if (event.target == modal) {
        modal.style.display = "none";
    }

    // 点击外部时关闭搜索结果 (also check if searchResults exists)
    if (searchResults &&
        event.target !== searchInput &&
        !event.target.matches('.search-button') && // Assuming searchBtn has this class or use its ID
        !searchResults.contains(event.target) && // More robust check for clicks within results
        searchResults.style.display === 'block' &&
        !document.getElementById('search-toggle-btn').contains(event.target) && // Don't hide if toggle is clicked
        !document.getElementById('chart-search-box').contains(event.target) // Don't hide if click is inside search box itself
    ) {
        // Only hide if search results are visible AND click is outside relevant search components
        // searchResults.style.display = "none"; // This logic is now handled by blur usually
    }
}

// 添加防抖动函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 优化后的搜索函数
const debouncedSearch = debounce(function () {
    searchNodes();
}, 300); // 300ms 的延迟

// 在页面加载后创建搜索框
function createSearchBox() {
    var chartContainer = document.querySelector('.chart-container[_echarts_instance_]');
    if (!chartContainer) {
        debugLog('无法找到图表容器，5秒后重试');
        setTimeout(createSearchBox, 5000);
        return;
    }

    debugLog(`找到图表容器: ${chartContainer.id}`);

    if (getComputedStyle(chartContainer).position !== 'relative') {
        chartContainer.style.position = 'relative';
        debugLog('已将图表容器设置为相对定位');
    }

    var searchWidgetContainer = document.createElement('div');
    searchWidgetContainer.id = 'search-widget-container';
    searchWidgetContainer.style.display = 'flex';
    searchWidgetContainer.style.flexDirection = 'column';
    searchWidgetContainer.style.alignItems = 'flex-start';
    chartContainer.appendChild(searchWidgetContainer);

    var searchToggleBtn = document.createElement('button');
    searchToggleBtn.id = 'search-toggle-btn';
    searchToggleBtn.textContent = '🔍';
    searchToggleBtn.style.width = '32px';
    searchToggleBtn.style.height = '32px';
    searchToggleBtn.style.display = 'inline-flex';
    searchToggleBtn.style.alignItems = 'center';
    searchToggleBtn.style.justifyContent = 'center';
    searchToggleBtn.style.marginBottom = '8px';
    searchToggleBtn.style.borderRadius = '6px';
    searchToggleBtn.style.border = 'none';
    searchToggleBtn.style.background = '#4b8bf4';
    searchToggleBtn.style.color = '#fff';
    searchToggleBtn.style.cursor = 'pointer';
    searchWidgetContainer.appendChild(searchToggleBtn);

    var searchBox = document.createElement('div');
    searchBox.id = 'chart-search-box';
    // Styling is primarily handled by CSS #chart-search-box and #chart-search-box.visible

    var inputContainer = document.createElement('div');
    inputContainer.style.display = 'flex';

    searchInput = document.createElement('input');
    searchInput.id = 'nodeSearchInput';
    searchInput.type = 'text';
    searchInput.placeholder = '输入节点名称搜索';
    // CSS will style searchInput via #chart-search-box #nodeSearchInput

    searchBtn = document.createElement('button');
    searchBtn.id = 'nodeSearchBtn';
    searchBtn.textContent = '搜索';
    // CSS will style searchBtn via #chart-search-box #nodeSearchBtn

    reset = document.createElement('button');
    reset.id = 'refreshButton';
    reset.textContent = '刷新页面';
    reset.setAttribute('onclick', 'location.reload()');
    // CSS will style reset via #chart-search-box #refreshButton

    searchResults = document.createElement('div');
    searchResults.id = 'searchResults';
    // CSS will style searchResults via #chart-search-box #searchResults
    // Initial display: none is implicitly handled by not being .visible or by JS logic

    inputContainer.appendChild(searchInput);
    inputContainer.appendChild(searchBtn);
    inputContainer.appendChild(reset);
    searchBox.appendChild(inputContainer);
    searchBox.appendChild(searchResults);
    searchWidgetContainer.appendChild(searchBox);

    debugLog('搜索框已添加到图表容器的部件内');

    searchToggleBtn.addEventListener('click', function () {
        if (searchBox.classList.contains('visible')) {
            searchBox.classList.remove('visible');
            searchToggleBtn.textContent = '🔍';
        } else {
            searchBox.classList.add('visible');
            searchToggleBtn.textContent = '✕';
        }
        if (!searchBox.classList.contains('visible')) {
            if (searchResults) {
                searchResults.style.display = 'none';
            }
        }
    });

    // 创建返回默认知识图谱按钮（放在搜索按钮下方）
    var backBtn = document.getElementById('backToDefaultKG');
    if (!backBtn) {
        backBtn = document.createElement('button');
        backBtn.id = 'backToDefaultKG';
        backBtn.textContent = '↩';
        backBtn.title = '返回默认知识图谱';
        backBtn.style.cssText = 'display:none; width:32px; height:32px; margin-top:8px; border:none; border-radius:6px; background:#4b8bf4; color:#fff; cursor:pointer; box-shadow:0 2px 6px rgba(0,0,0,0.2);';
        backBtn.onclick = function () {
            restoreDefaultGraph();
        };
    }
    searchWidgetContainer.appendChild(backBtn);

    searchBtn.onclick = function () {
        searchNodes();
    };

    searchInput.addEventListener('input', function () {
        debouncedSearch();
    });

    searchInput.addEventListener('keyup', function (event) {
        if (event.key === 'Enter') {
            var resultItems = document.querySelectorAll('#chart-search-box .search-result-item');
            if (resultItems.length === 1 && !resultItems[0].textContent.includes('无匹配结果')) {
                var nodeName = resultItems[0].getAttribute('data-name');
                focusNode(nodeName);
                searchResults.style.display = "none";
            }
        }
    });

    searchInput.addEventListener('focus', function () {
        if (this.value.trim() !== '' && searchBox.classList.contains('visible')) { // Only search if box is visible
            searchNodes();
        }
    });

    // Blur event to hide search results needs careful handling to allow clicks on results
    searchInput.addEventListener('blur', function () {
        // Use a small timeout to allow click on search result to register
        setTimeout(function () {
            if (!searchResults.matches(':hover')) { // Don't hide if mouse is over results
                // searchResults.style.display = "none"; // This might be too aggressive
            }
        }, 200);
    });
}

// 核心功能函数
// 1. 搜索节点
function searchNodes() {
    if (!searchInput || !searchResults) return; // Ensure elements exist
    var searchTerm = searchInput.value.trim().toLowerCase();
    if (searchTerm === "") {
        searchResults.style.display = "none";
        return;
    }

    debugLog(`搜索节点: ${searchTerm}`);

    var matchedNodes = rawData.nodes.filter(function (node) {
        return node.name.toLowerCase().includes(searchTerm) ||
            (node.des && node.des.toLowerCase().includes(searchTerm));
    });

    if (matchedNodes.length > 0) {
        var resultsHTML = "";
        matchedNodes.forEach(function (node) {
            resultsHTML += '<div class="search-result-item" data-name="' + node.name + '">' +
                node.name +
                (node.des ? ' <small>(' + node.des.substring(0, 30) + (node.des.length > 30 ? '...' : '') + ')</small>' : '') +
                '</div>';
        });
        searchResults.innerHTML = resultsHTML;
        searchResults.style.display = "block";

        var resultItems = document.querySelectorAll('#chart-search-box .search-result-item');
        resultItems.forEach(function (item) {
            item.addEventListener('click', function () {
                var nodeName = this.getAttribute('data-name');
                debugLog(`选择搜索结果: ${nodeName}`);
                focusNode(nodeName);
                searchResults.style.display = "none";
                // searchBox.classList.remove('visible'); // Optionally hide search box after selection
                // document.getElementById('search-toggle-btn').textContent = '🔍';
            });
        });
    } else {
        searchResults.innerHTML = '<div class="search-result-item">无匹配结果</div>';
        searchResults.style.display = "block";
    }
}

// 2. 聚焦节点及其相连节点
function focusNode(nodeName) {
    if (!myChart || !rawData.nodes.length) {
        debugLog('图表或数据未初始化，无法聚焦节点');
        return;
    }

    debugLog(`准备聚焦节点: ${nodeName}`);

    if (currentState.mode === 'focus' && currentState.focusedNode === nodeName) {
        debugLog('已经聚焦到此节点，恢复完整图谱');
        restoreFullGraph();
        return;
    }

    try {
        var targetNode = null;
        var linkedNodeNames = [];
        var option = myChart.getOption();
        var currentNodes = option.series[0].data;

        for (var i = 0; i < currentNodes.length; i++) {
            if (currentNodes[i].name === nodeName) {
                targetNode = currentNodes[i];
                break;
            }
        }

        if (!targetNode) {
            for (var i = 0; i < rawData.nodes.length; i++) {
                if (rawData.nodes[i].name === nodeName) {
                    targetNode = rawData.nodes[i];
                    break;
                }
            }
        }

        if (!targetNode) {
            debugLog(`未找到节点: ${nodeName}`);
            return;
        }

        for (var i = 0; i < rawData.links.length; i++) {
            if (rawData.links[i].source === nodeName) {
                linkedNodeNames.push(rawData.links[i].target);
            } else if (rawData.links[i].target === nodeName) {
                linkedNodeNames.push(rawData.links[i].source);
            }
        }

        debugLog(`找到 ${linkedNodeNames.length} 个相连节点`);

        var focusedNodes = [];
        var focusedLinks = [];

        focusedNodes.push(JSON.parse(JSON.stringify(targetNode)));

        for (var i = 0; i < rawData.nodes.length; i++) {
            if (linkedNodeNames.includes(rawData.nodes[i].name) || rawData.nodes[i].name === nodeName) {
                // Ensure the target node itself is included if not already added, and all linked nodes
                if (!focusedNodes.find(n => n.name === rawData.nodes[i].name)) {
                    focusedNodes.push(JSON.parse(JSON.stringify(rawData.nodes[i])));
                }
            }
        }

        for (var i = 0; i < rawData.links.length; i++) {
            if (rawData.links[i].source === nodeName || rawData.links[i].target === nodeName) {
                focusedLinks.push(JSON.parse(JSON.stringify(rawData.links[i])));
            }
        }

        option.series[0].data = focusedNodes;
        option.series[0].links = focusedLinks;

        for (var i = 0; i < focusedNodes.length; i++) {
            if (focusedNodes[i].name === nodeName) {
                focusedNodes[i].itemStyle = {
                    color: '#ff5500',
                    borderWidth: 5,
                    borderColor: '#ff9500'
                };
                focusedNodes[i].symbolSize = Math.max(focusedNodes[i].symbolSize || 10, 60); // Ensure it's large
                break;
            }
        }

        myChart.setOption(option, { replaceMerge: ['series'] });
        currentState.mode = 'focus';
        currentState.focusedNode = nodeName;
        debugLog(`节点聚焦完成: ${nodeName}`);
    } catch (error) {
        debugLog(`聚焦节点失败: ${error.message}`);
        console.error(error);
        setTimeout(restoreFullGraph, 500);
    }
}

// 3. 恢复完整图谱
function restoreFullGraph() {
    if (!myChart || !rawData.nodes.length) {
        debugLog('图表或数据未初始化');
        return;
    }
    debugLog('恢复完整图谱');
    try {
        var option = myChart.getOption();
        var nodesCopy = JSON.parse(JSON.stringify(rawData.nodes));
        var linksCopy = JSON.parse(JSON.stringify(rawData.links));
        option.series[0].data = nodesCopy;
        option.series[0].links = linksCopy;
        myChart.setOption(option, { replaceMerge: ['series'] });
        currentState.mode = 'full';
        currentState.focusedNode = null;
        debugLog('已恢复完整图谱');
    } catch (error) {
        debugLog(`恢复图谱失败: ${error.message}`);
        console.error(error);
    }
}

// 4. 显示节点详情
function showNodeDetails(nodeName) {
    if (!nodeName || !modal || !modalTitle || !modalBody) return;
    debugLog(`显示节点详情: ${nodeName}`);
    var nodeData = rawData.nodes.find(node => node.name === nodeName);

    if (!nodeData) {
        debugLog(`未找到节点详情: ${nodeName}`);
        return;
    }

    modalTitle.innerText = nodeData.name || "节点详情";
    var content = "";

    // 删去知识节点详情中的
    //if (nodeData.category !== undefined && typeof nodeData.category === 'string' && nodeData.category.trim() !== '') {
    //    content += "<p><strong>分类：</strong>" + nodeData.category + "</p>";
    //} else if (typeof nodeData.category === 'number' && categoriesCache[nodeData.category] !== undefined) {
    //     content += "<p><strong>分类：</strong>" + categoriesCache[nodeData.category].name + "</p>"; // Assuming categoriesCache stores objects with name property
    //} else if (nodeData.category !== undefined) {
    //   debugLog(`未知或无效的分类值: ${nodeData.category}, 类型: ${typeof nodeData.category}`);
    //    content += "<p><strong>分类：</strong>未知分类</p>";
    //}

    if (nodeData.des) {
        content += "<p><strong>描述：</strong>" + nodeData.des + "</p>";
    }

    for (var key in nodeData) {
        if (["name", "des", "category", "symbolSize", "x", "y", "fixed", "id", "index", "value", "label", "itemStyle"].indexOf(key) === -1) {
            content += "<p><strong>" + key + "：</strong>" + nodeData[key] + "</p>";
        }
    }

    content += `<div style="margin-top: 20px; text-align: center; display: flex; justify-content: center; gap: 15px;">` +
        (isGeneratedGraph ? '' : `<button id="generateKGBtn" style="padding: 8px 16px; background-color: #4b8bf4; color: white; 
            border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">生成知识图谱</button>`) +
        `<button id="recommendResourcesBtn" style="padding: 8px 16px; background-color: #4caf50; color: white; 
            border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">推荐学习资源</button>
        </div>
        <div id="kgStatus" style="margin-top: 10px; font-size: 14px; display: none;"></div>
        <div id="resourcesContainer" style="margin-top: 15px; display: none;">
            <h3 style="font-size: 16px; margin-bottom: 10px;">推荐学习资源</h3>
            <div id="resourcesList" style="max-height: 200px; overflow-y: auto;"></div>
        </div>`;

    modalBody.innerHTML = content || "<p>没有详细信息</p>";
    modal.style.display = "block";

    var generateKGBtn = document.getElementById('generateKGBtn');
    if (generateKGBtn) {
        generateKGBtn.onclick = function () { // Changed to onclick to avoid multiple event listeners if modal re-opens
            generateKnowledgeGraph(nodeData.name);
        };
    }

    var recommendResourcesBtn = document.getElementById('recommendResourcesBtn');
    if (recommendResourcesBtn) {
        recommendResourcesBtn.onclick = function () { // Changed to onclick
            getRecommendedResources(nodeData.name);
        };
    }
}

// 生成知识图谱的函数
function generateKnowledgeGraph(keyword) {
    if (isGeneratedGraph) {
        debugLog('当前已展示生成的知识图谱，忽略重复生成请求');
        return;
    }
    if (!keyword) return;

    // ✨✨✨ 在这里添加这行代码以修复错误 ✨✨✨
    const AppConfig = getAppConfig();

    var statusEl = document.getElementById('kgStatus');
    if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.textContent = `正在为 "${keyword}" 生成知识图谱，请稍候...`;
    }
    const apiUrl = AppConfig.API_BASE_URL + '/generate_kg';
    debugLog(`开始为 "${keyword}" 生成知识图谱，使用URL: ${apiUrl}`);

    fetch(apiUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            keyword: keyword,
            display_mode: 'current_page',
            source_file: window.location.pathname.split('/').pop()
        })
    })
        .then(response => {
            debugLog(`收到服务器响应: 状态${response.status}`);
            if (!response.ok) {
                throw new Error(`网络请求失败，状态码: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            debugLog(`解析响应数据: ${JSON.stringify(data).substring(0, 100)}...`);
            if (data.display_mode === 'current_page' && data.nodes && data.links) {
                updateChartWithNewData(data.nodes, data.links, keyword);
                isGeneratedGraph = true;
                toggleBackButton(true);
                if (statusEl) {
                    statusEl.textContent = `知识图谱已更新！`;
                    setTimeout(function () { modal.style.display = "none"; }, 1500);
                }
            } else if (data.html_path) { // Check for html_path for new page mode
                if (statusEl) {
                    statusEl.textContent = `知识图谱生成成功！`;
                    setTimeout(function () {
                        statusEl.innerHTML = `知识图谱生成成功！<a href="${data.html_path}" target="_blank" 
                            style="margin-left: 10px; color: #4b8bf4; text-decoration: underline;">点击查看</a>`;
                    }, 1000);
                }
            } else {
                throw new Error('服务器响应数据格式不正确');
            }
            debugLog(`知识图谱处理完成`);
        })
        .catch(error => {
            debugLog(`知识图谱生成失败: ${error.message}`);
            console.error('知识图谱生成错误:', error);
            if (statusEl) {
                statusEl.textContent = `生成失败: ${error.message}`;
                statusEl.style.color = 'red';
            }
            // Fallback data (optional, if you want to show something on failure)
            // var fallbackData = { nodes: [{name: keyword, symbolSize: 70, category: 0}], links: [] };
            // updateChartWithNewData(fallbackData.nodes, fallbackData.links, keyword);
        });
}

// 使用新数据更新图表
function updateChartWithNewData(newNodes, newLinks, centerNodeName) {
    if (!myChart) {
        debugLog('图表实例不存在，无法更新');
        return;
    }
    debugLog(`使用新数据更新图表，中心节点: ${centerNodeName}`);
    try {
        var processedNodes = newNodes.map(node => {
            if (node.name === centerNodeName) {
                node.symbolSize = Math.max(node.symbolSize || 10, 70); // Ensure center is large
                node.category = typeof node.category === 'string' ? node.category : (categoriesCache[0] ? categoriesCache[0].name : 0); // Assign first category if numeric or keep string
            } else {
                node.symbolSize = node.symbolSize || 50;
            }
            // Ensure category is a string if categoriesCache is of {name:string} objects
            if (typeof node.category === 'number' && categoriesCache[node.category]) {
                node.category = categoriesCache[node.category].name;
            }
            return node;
        });

        var option = myChart.getOption();
        option.series[0].data = processedNodes;
        option.series[0].links = newLinks;
        // Potentially update categories in legend if they changed
        // var newCategoryNames = Array.from(new Set(processedNodes.map(n => n.category).filter(Boolean)));
        // option.legend[0].data = newCategoryNames;
        // option.series[0].categories = newCategoryNames.map(name => ({name: name}));

        myChart.setOption(option, { replaceMerge: ['series', 'legend'] });

        rawData.nodes = JSON.parse(JSON.stringify(processedNodes)); // Update rawData
        rawData.links = JSON.parse(JSON.stringify(newLinks));
        rawData.categories = option.series[0].categories || rawData.categories;

        currentState.mode = 'full';
        currentState.focusedNode = null;
        debugLog(`图表更新成功，共 ${processedNodes.length} 个节点，${newLinks.length} 个连接`);
    } catch (error) {
        debugLog(`更新图表失败: ${error.message}`);
        console.error('更新图表错误:', error);
    }
}

// 切换返回按钮显隐
function toggleBackButton(show) {
    var btn = document.getElementById('backToDefaultKG');
    if (btn) {
        btn.style.display = show ? 'block' : 'none';
    }
}

// 恢复默认图谱
function restoreDefaultGraph() {
    if (defaultGraph.nodes.length === 0) {
        debugLog('默认图谱数据为空，重新加载');
        loadAndRenderGraph();
        return;
    }
    isGeneratedGraph = false;
    toggleBackButton(false);
    updateChartWithNewData(
        JSON.parse(JSON.stringify(defaultGraph.nodes)),
        JSON.parse(JSON.stringify(defaultGraph.links)),
        defaultGraph.nodes[0] ? defaultGraph.nodes[0].name : ''
    );
    // 恢复分类
    option_4ed221bd03f84e8b9227cdd3d973b8bc.series[0].categories = JSON.parse(JSON.stringify(defaultGraph.categories));
    option_4ed221bd03f84e8b9227cdd3d973b8bc.legend[0].data = defaultGraph.categories.map(c => c.name);
    // 可选：重新应用学习状态
    if (typeof applyNodeStatusesToChart === 'function') {
        applyNodeStatusesToChart();
    }
}

// 学习状态颜色映射
const learningStatusColors = {
    'not_started': '#888888', // 灰色 (此颜色不再直接使用，但保留键值以供逻辑判断)
    'in_progress': '#ff9900', // 橙色
    'completed': '#4caf50',   // 绿色
    'review_needed': '#f44336' // 红色
};

// 存储节点学习状态
var nodeStatusMap = {};

// 将节点状态应用到图表和rawData的通用函数
function applyNodeStatusesToChart() {
    if (!myChart || !Object.keys(nodeStatusMap).length) {
        debugLog('图表未初始化或无状态数据，跳过应用颜色。');
        return;
    }
    try {
        debugLog(`正在将 ${Object.keys(nodeStatusMap).length} 个节点状态应用到图表...`);
        const option = myChart.getOption();
        if (!option.series[0] || !option.series[0].data) {
            debugLog('图表数据尚未加载，无法应用状态颜色。');
            return;
        }
        const currentNodes = option.series[0].data;

        // 更新当前图表选项中的节点
        const updatedNodes = currentNodes.map(node => {
            const status = nodeStatusMap[node.name];
            if (status) {
                if (!node.itemStyle) node.itemStyle = {};

                // ✨✨✨ 更新点 ✨✨✨
                // 如果状态是“未开始”，则删除颜色属性以恢复默认颜色
                if (status === 'not_started') {
                    delete node.itemStyle.color;
                }
                // 否则，应用在颜色映射中定义好的颜色
                else if (learningStatusColors[status]) {
                    node.itemStyle.color = learningStatusColors[status];
                }
            }
            return node;
        });

        option.series[0].data = updatedNodes;
        myChart.setOption(option, { notMerge: false, replaceMerge: ['series'] });

        // 同时更新原始数据 rawData 以保证状态一致性
        rawData.nodes.forEach(node => {
            const status = nodeStatusMap[node.name];
            if (status) {
                if (!node.itemStyle) node.itemStyle = {};

                // ✨✨✨ 更新点 ✨✨✨
                if (status === 'not_started') {
                    delete node.itemStyle.color;
                } else if (learningStatusColors[status]) {
                    node.itemStyle.color = learningStatusColors[status];
                }
            }
        });
        debugLog('节点状态颜色应用完成。');
    } catch (error) {
        debugLog(`应用节点状态时出错: ${error.message}`);
        console.error('应用节点状态时出错:', error);
    }
}

// 从服务器获取最新的学习状态并应用
function fetchAndApplyNodeStatuses(AppConfig) { // <-- 接收 AppConfig 作为参数
    const apiUrl = `${AppConfig.API_BASE_URL}/get_kg_learn_state?student_id=${AppConfig.studentId}&course_name=${encodeURIComponent(AppConfig.className)}`;
    debugLog(`正在从服务器获取最新学习状态: ${apiUrl}`);

    fetch(apiUrl)
        .then(response => {
            if (!response.ok) {
                throw new Error(`网络请求失败: ${response.status} ${response.statusText}`);
            }
            return response.json();
        })
        .then(statusData => {
            debugLog('成功从服务器获取学习状态数据。');

            nodeStatusMap = statusData;

            localStorage.setItem('nodeStatusMap', JSON.stringify(nodeStatusMap));
            debugLog(`最新状态已存入 localStorage，共 ${Object.keys(nodeStatusMap).length} 条记录。`);

            applyNodeStatusesToChart();
        })
        .catch(error => {
            console.error('获取学习状态失败:', error);
            debugLog(`获取服务端学习状态失败: ${error.message}. 页面将继续使用本地缓存（如果存在）。`);
        });
}


// 右键菜单相关变量
var contextMenu = document.getElementById('contextMenu');
var currentRightClickedNode = null;

// 初始化右键菜单事件
function initContextMenu() {
    var chartContainer = document.querySelector('.chart-container');
    if (chartContainer) {
        console.log("已找到图表容器，绑定右键菜单事件");
    } else {
        console.error('警告: 未找到图表容器元素');
        debugLog('警告: 未找到图表容器元素');
    }

    document.addEventListener('click', function () {
        if (contextMenu) {
            contextMenu.style.display = 'none';
        }
    });

    var menuItems = document.querySelectorAll('.menu-item');
    console.log(`找到${menuItems.length}个菜单项`);
    menuItems.forEach(function (item) {
        item.addEventListener('click', function () {
            console.log(`点击菜单项: ${this.getAttribute('data-status')}`);
            if (currentRightClickedNode) {
                var status = this.getAttribute('data-status');
                console.log(`准备更新节点 "${currentRightClickedNode}" 的学习状态为: ${status}`);
                updateNodeLearningStatus(currentRightClickedNode, status);
            } else {
                console.error("错误: currentRightClickedNode为空");
            }
            contextMenu.style.display = 'none';
        });

        item.addEventListener('mouseover', function () {
            this.style.backgroundColor = '#f0f0f0';
        });

        item.addEventListener('mouseout', function () {
            this.style.backgroundColor = 'transparent';
        });
    });

    debugLog('右键菜单初始化完成');
    console.log('右键菜单初始化完成');
}


// 更新节点学习状态（保存至服务器，并处理错误）
function updateNodeLearningStatus(nodeName, status) {
    // 基础校验
    if (!myChart || !rawData || !rawData.nodes || !rawData.nodes.length) {
        console.error('图表或数据未初始化，无法更新节点状态');
        if (typeof debugLog === 'function') debugLog('图表或数据未初始化，无法更新节点状态');
        return;
    }

    // ---- 1) 无变化短路：若目标状态与当前状态一致，则直接返回 ----
    // 规范化比较，避免大小写/空白差异
    var normalize = function (s) { return s == null ? null : String(s).trim().toLowerCase(); };
    var targetStatus = normalize(status);

    // 先从内存中的 nodeStatusMap 读
    var currentStatus = null;
    try {
        if (typeof nodeStatusMap === 'object' && nodeStatusMap) {
            currentStatus = nodeStatusMap[nodeName];
        }
        // 再尝试从 localStorage 兜底（防止刷新后内存丢失）
        if (currentStatus == null) {
            var cached = localStorage.getItem('nodeStatusMap');
            if (cached) {
                try {
                    var obj = JSON.parse(cached);
                    if (obj && typeof obj === 'object') currentStatus = obj[nodeName];
                } catch (e) { }
            }
        }
        // 最后根据图上节点的颜色反推（没有颜色则视为 not_started）
        if (currentStatus == null) {
            var node = (rawData.nodes || []).find(function (n) { return n.name === nodeName; });
            if (node) {
                var color = node.itemStyle && node.itemStyle.color;
                if (!color) {
                    currentStatus = 'not_started';
                } else if (typeof learningStatusColors === 'object' && learningStatusColors) {
                    // 颜色 -> 状态的反查
                    for (var k in learningStatusColors) {
                        if (learningStatusColors.hasOwnProperty(k) && learningStatusColors[k] === color) {
                            currentStatus = k;
                            break;
                        }
                    }
                }
            }
        }
    } catch (e) {
        // 比对失败不影响后续流程（当作未知，需要继续更新）
        console.warn('状态比对失败，继续执行更新流程：', e);
    }

    if (normalize(currentStatus) === targetStatus) {
        console.log(`节点 "${nodeName}" 状态未变化（仍为 "${targetStatus}"），跳过网络请求。`);
        if (typeof debugLog === 'function') debugLog(`节点 "${nodeName}" 状态未变化，已跳过请求`);
        return; // ←←← 直接结束函数
    }

    // ---- 2) 正常发起更新请求 ----
    console.log(`准备将节点 "${nodeName}" 的学习状态 "${status}" 上传至服务器...`);
    if (typeof debugLog === 'function') debugLog(`准备将节点 "${nodeName}" 的学习状态 "${status}" 上传至服务器...`);

    var AppConfig = getAppConfig();
    var apiUrl = AppConfig.API_BASE_URL + '/update_kg_learn_state';
    var postData = {
        student_id: AppConfig.studentId,
        course_name: AppConfig.className,
        point_name: nodeName,
        state: status
    };

    fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(postData)
    })
        .then(function (response) {
            if (!response.ok) {
                return response.text().then(function (text) {
                    throw new Error(`服务器响应错误: ${response.status} ${text}`);
                });
            }
            return response.json();
        })
        .then(function (data) {
            console.log('服务器响应:', data);
            if (typeof debugLog === 'function') debugLog(`服务器响应: ${JSON.stringify(data)}`);

            if (data.status === 'success') {
                console.log('服务器确认保存成功。');

                // 同步本地状态
                if (typeof nodeStatusMap !== 'object' || !nodeStatusMap) window.nodeStatusMap = {};
                nodeStatusMap[nodeName] = status;
                localStorage.setItem('nodeStatusMap', JSON.stringify(nodeStatusMap));

                // 更新图上节点样式
                var option = myChart.getOption();
                var updatedNodes = option.series[0].data.map(function (node) {
                    if (node.name === nodeName) {
                        node.itemStyle = node.itemStyle || {};
                        if (status === 'not_started') {
                            delete node.itemStyle.color;
                        } else {
                            node.itemStyle.color = learningStatusColors[status];
                        }
                        if (currentState.mode === 'focus' && currentState.focusedNode === nodeName) {
                            node.itemStyle.borderWidth = 5;
                            node.itemStyle.borderColor = '#ff9500';
                        }
                    }
                    return node;
                });

                // option.series[0].data = updatedNodes;
                // myChart.setOption(option, { notMerge: false, replaceMerge: ['series'] });

                myChart.setOption({ series: [{ data: updatedNodes }] });

                // 同步原始数据的颜色
                rawData.nodes.forEach(function (node) {
                    if (node.name === nodeName) {
                        node.itemStyle = node.itemStyle || {};
                        if (status === 'not_started') {
                            delete node.itemStyle.color;
                        } else {
                            node.itemStyle.color = learningStatusColors[status];
                        }
                    }
                });

                console.log(`节点 "${nodeName}" 状态已成功更新并同步至服务器。`);
                if (typeof debugLog === 'function') debugLog(`节点 "${nodeName}" 状态更新成功`);
            } else if (data.status === 'fail' && data.message && data.message.indexOf('学生未找到') !== -1) {
                console.warn(`保存失败: ${data.message}`);
                alert(`学号 ${AppConfig.studentId} 信息未在数据库中找到，保存失败。\n您的学习记录本次将不会被保存。`);
            } else {
                console.error('服务器返回操作失败:', data.message);
                alert(`保存学习状态失败: ${data.message || '未知服务器错误'}`);
            }
        })
        .catch(function (error) {
            console.error('更新学习状态时发生网络或客户端错误:', error);
            if (typeof debugLog === 'function') debugLog(`更新学习状态失败: ${error.message}`);
            alert(`保存学习状态失败，请检查网络连接或联系管理员。\n错误详情: ${error.message}`);
        });
}




// 从本地存储加载节点状态
function loadNodeStatuses() {
    try {
        var savedStatusMap = localStorage.getItem('nodeStatusMap');
        if (savedStatusMap) {
            nodeStatusMap = JSON.parse(savedStatusMap);
            debugLog(`从本地存储(缓存)加载了 ${Object.keys(nodeStatusMap).length} 个节点状态`);

            applyNodeStatusesToChart();
        }
    } catch (error) {
        debugLog(`从本地存储加载节点状态失败: ${error.message}`);
        console.error('加载节点状态错误:', error);
        localStorage.removeItem('nodeStatusMap');
    }
}


// 页面加载完成后初始化图表交互
document.addEventListener('DOMContentLoaded', function () {
    debugLog('DOM加载完成，初始化图表交互');

    initContextMenu();

        setTimeout(function () {
            var chartElements = document.querySelectorAll('[_echarts_instance_]');
            if (chartElements.length > 0) {
                var chartDom = chartElements[0];
                myChart = echarts.getInstanceByDom(chartDom);

            var chartContainer = chartDom.parentNode;
            if (chartContainer && getComputedStyle(chartContainer).position === 'static') {
                chartContainer.style.position = 'relative'; // Ensure parent is positioned for absolute children
            }
            createSearchBox();

            if (myChart) {
                debugLog('成功获取图表实例');
                var option = myChart.getOption();

                if (option.legend && option.legend[0] && option.legend[0].data) {
                    categoriesCache = option.legend[0].data.map(cat => typeof cat === 'string' ? { name: cat } : cat);
                    debugLog(`已缓存${categoriesCache.length}个分类(来自legend): ${categoriesCache.map(c => c.name).join(', ')}`);
                } else if (option.series && option.series[0] && option.series[0].categories) {
                    categoriesCache = option.series[0].categories;
                    debugLog(`已缓存${categoriesCache.length}个分类(来自series): ${categoriesCache.map(c => c.name).join(', ')}`);
                }

                if (option.series[0].data && option.series[0].links) {
                    rawData.nodes = JSON.parse(JSON.stringify(option.series[0].data));
                    rawData.links = JSON.parse(JSON.stringify(option.series[0].links));
                    debugLog(`初始化完成，共 ${rawData.nodes.length} 个节点，${rawData.links.length} 个连接`);
                } else {
                    debugLog('ERROR: 图表数据结构不完整');
                }

                var clickTimer = null;
                var clickDelay = 300;

                myChart.off('click');
                myChart.on('click', function (params) {
                    if (params.dataType === 'node') {
                        var nodeName = params.data.name;
                        if (clickTimer) {
                            clearTimeout(clickTimer);
                            clickTimer = null;
                            return;
                        }
                        clickTimer = setTimeout(function () {
                            clickTimer = null;
                            debugLog(`单击节点: ${nodeName}`);
                            showNodeDetails(nodeName);
                        }, clickDelay);
                    }
                });

                myChart.off('dblclick');
                myChart.on('dblclick', function (params) {
                    if (params.dataType === 'node') {
                        var nodeName = params.data.name;
                        if (clickTimer) {
                            clearTimeout(clickTimer);
                            clickTimer = null;
                        }
                        debugLog(`双击节点: ${nodeName}`);
                        if (currentState.mode === 'focus' && currentState.focusedNode === nodeName) {
                            restoreFullGraph();
                        } else {
                            focusNode(nodeName);
                        }
                    }
                });

                myChart.off('contextmenu');
                myChart.on('contextmenu', function (params) {
                    params.event.event.preventDefault();

                    console.log(`图表contextmenu事件触发:`, params);
                    if (params.dataType === 'node') {
                        var nodeName = params.data.name;
                        currentRightClickedNode = nodeName;
                        console.log(`右键点击节点: ${currentRightClickedNode}, 事件坐标: (${params.event.offsetX}, ${params.event.offsetY})`);
                        debugLog(`右键点击节点: ${currentRightClickedNode}`);

                        var chartContainer = document.querySelector('.chart-container');
                        var rect = chartContainer.getBoundingClientRect();

                        var menuX = rect.left + params.event.offsetX;
                        var menuY = rect.top + params.event.offsetY;

                        contextMenu.style.left = menuX + 'px';
                        contextMenu.style.top = menuY + 'px';
                        contextMenu.style.display = 'block';
                        console.log(`右键菜单已显示在位置 (${menuX}, ${menuY})`);

                        var currentStatus = nodeStatusMap[currentRightClickedNode];
                        console.log(`当前节点状态: ${currentStatus}`);
                        var menuItems = document.querySelectorAll('.menu-item');
                        menuItems.forEach(function (item) {
                            var status = item.getAttribute('data-status');
                            if (status === currentStatus) {
                                item.style.backgroundColor = '#f0f0f0';
                                item.style.fontWeight = 'bold';
                            } else {
                                item.style.backgroundColor = 'transparent';
                                item.style.fontWeight = 'normal';
                            }
                        });
                    }
                });

                debugLog('交互事件绑定完成');
                console.log('交互事件绑定完成');

                loadNodeStatuses();
            } else {
                debugLog('ERROR: 未能获取图表实例');
            }
        } else {
            debugLog('ERROR: 未找到图表元素，500ms后重试');
        }
    }, 500);
});


// 添加获取推荐学习资源的函数
function getRecommendedResources(keyword) {
    if (!keyword) return;

    var resourcesContainer = document.getElementById('resourcesContainer');
    var resourcesList = document.getElementById('resourcesList');

    if (resourcesContainer && resourcesList) {
        resourcesContainer.style.display = 'block';
        resourcesList.innerHTML = '<p style="text-align: center;">正在获取推荐资源...</p>';

        const AppConfig = getAppConfig();

        const apiUrl = AppConfig.API_BASE_URL + '/search/' + encodeURIComponent(keyword);
        debugLog(`开始为 "${keyword}" 获取推荐学习资源，使用URL: ${apiUrl}`);

        fetch(apiUrl)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`网络请求失败，状态码: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                debugLog(`解析响应数据 (资源): ${JSON.stringify(data).substring(0, 100)}...`);
                if (data.result && data.result.length > 0) {
                    var html = '<ul style="list-style: none; padding: 0; margin: 0;">';
                    data.result.forEach(function (resource, index) {
                        html += `<li style="padding: 8px 10px; margin-bottom: 8px; border-radius: 4px; background-color: #f5f5f5;">
                                        <a href="${resource.url}" target="_blank" style="color: #4b8bf4; text-decoration: none; font-weight: bold;">
                                            ${index + 1}. ${resource.name}
                                        </a>
                                    </li>`;
                    });
                    html += '</ul>';
                    resourcesList.innerHTML = html;
                } else {
                    resourcesList.innerHTML = '<p style="text-align: center;">没有找到相关学习资源</p>';
                }
            })
            .catch(error => {
                debugLog(`获取推荐资源失败: ${error.message}`);
                resourcesList.innerHTML = `<p style="text-align: center; color: red;">获取失败: ${error.message}</p>`;
            });
    }
}
