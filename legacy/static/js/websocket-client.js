class RollWebSocketClient {
  constructor(activityId) {
    this.activityId = activityId;
    this.ws = null;
    this.isConnected = false;
    
    this.init();
  }
  
  init() {
    var protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    var host = window.location.host;
    var wsUrl = protocol + "//" + host + "/ws/" + this.activityId;
    
    try {
      this.ws = new WebSocket(wsUrl);
      this.setupEventHandlers();
    } catch (error) {
      console.error("WebSocket初始化失败:", error);
    }
  }
  
  setupEventHandlers() {
    var self = this;
    
    this.ws.onopen = function() {
      console.log("WebSocket连接已建立");
      self.isConnected = true;
    };
    
    this.ws.onmessage = function(event) {
      try {
        var data = JSON.parse(event.data);
        self.handleMessage(data);
      } catch (error) {
        console.error("解析WebSocket消息失败:", error);
      }
    };
    
    this.ws.onclose = function() {
      console.log("WebSocket连接已关闭");
      self.isConnected = false;
      
      setTimeout(function() {
        console.log("尝试重连WebSocket");
        self.init();
      }, 3000);
    };
    
    this.ws.onerror = function(error) {
      console.error("WebSocket发生错误:", error);
      self.isConnected = false;
    };
  }
  
  handleMessage(data) {
    if (data.type === "roll_result") {
      this.updateRollResult(data.result);
    } else if (data.type === "roll_deleted") {
      this.handleRollDeleted(data.result_id);
    } else if (data.type === "activity_ended") {
      this.handleActivityEnded();
    } else if (data.type === "activity_deleted") {
      this.handleActivityDeleted();
    } else {
      console.warn("未知的消息类型:", data.type);
    }
  }
  
  updateRollResult(result) {
    var leaderboardBody = document.getElementById("leaderboard-body");
    if (!leaderboardBody) {
      console.warn("未找到排行榜表格");
      return;
    }
    
    var newRow = this.createResultRow(result);
    
    var existingRow = leaderboardBody.querySelector("tr[data-result-id='" + result.id + "']");
    if (existingRow) {
      existingRow.replaceWith(newRow);
    } else {
      leaderboardBody.appendChild(newRow);
    }
    
    this.updateRankings();
    
    newRow.style.opacity = "0";
    newRow.style.transform = "translateY(20px)";
    newRow.style.transition = "all 0.5s ease-out";
    
    setTimeout(function() {
      newRow.style.opacity = "1";
      newRow.style.transform = "translateY(0)";
    }, 100);
  }
  
  createResultRow(result) {
    var row = document.createElement("tr");
    row.setAttribute("data-result-id", result.id);
    row.className = "hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors duration-150";
    
    var isAdminView = document.querySelector(".ip-cell") !== null;
    
    var rowHTML = "";
    rowHTML += '<td class="px-6 py-4 whitespace-nowrap"><span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 font-bold">?</span></td>';
    rowHTML += '<td class="px-6 py-4 whitespace-nowrap text-gray-900 dark:text-white font-medium">' + result.name + '</td>';
    rowHTML += '<td class="px-6 py-4 whitespace-nowrap"><div class="flex items-center gap-2"><strong class="text-2xl text-primary">' + result.number + '</strong>';
    if (result.rank === 1) {
      rowHTML += '<span class="px-2 py-1 bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 rounded text-xs font-medium">胜出</span>';
    }
    rowHTML += '</div></td>';
    
    if (isAdminView) {
      rowHTML += '<td class="px-6 py-4 whitespace-nowrap text-gray-600 dark:text-gray-400 ip-cell">' + result.ip + '</td>';
      rowHTML += '<td class="px-6 py-4 whitespace-nowrap"><form action="/admin/delete_roll/' + (result.activity_id || this.activityId) + '/' + (result.rank - 1) + '" method="post" class="inline"><button type="submit" onclick="return confirm(\'确定要删除该Roll点结果吗？此操作不可恢复。\')" class="px-3 py-1 bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 rounded text-xs font-medium hover:bg-red-200 dark:hover:bg-red-800 transition-colors duration-150">删除</button></form></td>';
    }
    
    row.innerHTML = rowHTML;
    return row;
  }
  
  updateRankings() {
    var leaderboardBody = document.getElementById("leaderboard-body");
    if (!leaderboardBody) return;
    
    var rows = Array.from(leaderboardBody.querySelectorAll("tr"));
    
    rows.sort(function(a, b) {
      var numA = parseInt(a.querySelector("strong").textContent);
      var numB = parseInt(b.querySelector("strong").textContent);
      return numB - numA;
    });
    
    rows.forEach(function(row, index) {
      var rank = index + 1;
      
      var rankCell = row.querySelector("td:first-child");
      var rankBadge = "";
      
      if (rank === 1) {
        rankBadge = '<span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-yellow-400 text-yellow-900 font-bold">1</span>';
      } else if (rank === 2) {
        rankBadge = '<span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-gray-400 text-gray-900 font-bold">2</span>';
      } else if (rank === 3) {
        rankBadge = '<span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-amber-600 text-amber-100 font-bold">3</span>';
      } else {
        rankBadge = '<span class="inline-flex items-center justify-center w-8 h-8 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 font-bold">' + rank + '</span>';
      }
      
      rankCell.innerHTML = rankBadge;
      
      var numberCell = row.querySelector("td:nth-child(3)");
      var number = numberCell.querySelector("strong").textContent;
      var numberHTML = '<div class="flex items-center gap-2"><strong class="text-2xl text-primary">' + number + '</strong>';
      if (rank === 1) {
        numberHTML += '<span class="px-2 py-1 bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 rounded text-xs font-medium">胜出</span>';
      }
      numberHTML += '</div>';
      numberCell.innerHTML = numberHTML;
    });
    
    rows.forEach(function(row) {
      leaderboardBody.appendChild(row);
    });
  }
  
  handleRollDeleted(resultId) {
    var leaderboardBody = document.getElementById("leaderboard-body");
    if (!leaderboardBody) return;
    
    var rowToDelete = leaderboardBody.querySelector("tr[data-result-id='" + resultId + "']");
    var self = this;
    
    if (rowToDelete) {
      rowToDelete.style.opacity = "0";
      rowToDelete.style.transform = "translateY(-20px)";
      rowToDelete.style.transition = "all 0.5s ease-out";
      
      setTimeout(function() {
        rowToDelete.remove();
        self.updateRankings();
      }, 500);
    }
  }
  
  handleActivityEnded() {
    var formContainer = document.querySelector(".glass-effect");
    if (formContainer) {
      formContainer.innerHTML = '<h2 class="text-2xl font-semibold mb-6 text-gray-800 dark:text-gray-200">参与Roll点</h2><div class="text-center py-8 bg-red-100 dark:bg-red-900/20 rounded-lg text-red-800 dark:text-red-200"><p>活动已结束，无法继续参与Roll点。</p></div>';
    }
  }
  
  handleActivityDeleted() {
    alert("活动已被删除，即将返回首页。");
    window.location.href = "/";
  }
  
  sendMessage(message) {
    if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn("WebSocket未连接，无法发送消息");
    }
  }
  
  close() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

document.addEventListener("DOMContentLoaded", function() {
  var activityIdMeta = document.querySelector("meta[name='activity-id']");
  if (activityIdMeta) {
    var activityId = activityIdMeta.getAttribute("content");
    if (activityId) {
      window.rollWebSocketClient = new RollWebSocketClient(activityId);
    }
  }
});
