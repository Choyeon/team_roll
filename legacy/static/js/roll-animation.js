class RollAnimation {
  constructor() {
    this.isAnimating = false;
    this.animationDuration = 3000;
    this.realResult = null;
    this.playerName = "";
    this.submitButton = null;
    this.originalText = "";
    this.formData = null;
    this.formAction = "";
  }

  showRollAnimation(playerName, submitButton, originalText, formData, formAction) {
    if (this.isAnimating) return;

    this.isAnimating = true;
    this.playerName = playerName;
    this.submitButton = submitButton;
    this.originalText = originalText;
    this.formData = formData;
    this.formAction = formAction;
    this.realResult = null;

    const modal = document.createElement("div");
    modal.className = "fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-80 backdrop-blur-sm";
    modal.style.zIndex = "99999";
    
    const container = document.createElement("div");
    container.className = "bg-gradient-to-br from-gray-800 to-gray-900 rounded-2xl p-8 max-w-md w-full shadow-2xl border border-gray-700 relative";
    
    const topBar = document.createElement("div");
    topBar.className = "absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-purple-500 to-blue-500 transition-all duration-500";
    container.appendChild(topBar);
    
    const title = document.createElement("h2");
    title.className = "text-3xl font-bold text-white mb-2 text-center";
    title.textContent = "ROLL点结果";
    container.appendChild(title);
    
    const playerNameEl = document.createElement("div");
    playerNameEl.className = "text-xl text-blue-400 mb-6 text-center";
    playerNameEl.textContent = playerName;
    container.appendChild(playerNameEl);
    
    const numberContainer = document.createElement("div");
    numberContainer.className = "bg-black bg-opacity-30 rounded-xl p-6 mb-6 border border-gray-700";
    
    const rollNumber = document.createElement("div");
    rollNumber.className = "text-6xl font-extrabold text-white text-center drop-shadow-lg transition-all duration-0.3s";
    rollNumber.textContent = "?";
    numberContainer.appendChild(rollNumber);
    container.appendChild(numberContainer);
    
    const qualityText = document.createElement("div");
    qualityText.className = "bg-blue-900 bg-opacity-30 text-blue-400 px-6 py-2 rounded-full text-lg font-semibold mb-6 inline-block mx-auto border border-blue-700";
    qualityText.textContent = "ROLL点中...";
    container.appendChild(qualityText);
    
    const progressContainer = document.createElement("div");
    progressContainer.className = "w-full h-2 bg-black bg-opacity-30 rounded-full overflow-hidden mb-2";
    
    const progressBar = document.createElement("div");
    progressBar.className = "h-full bg-gradient-to-r from-purple-500 to-blue-500 rounded-full transition-all duration-3000 linear shadow-lg";
    progressBar.style.width = "0%";
    progressContainer.appendChild(progressBar);
    container.appendChild(progressContainer);
    
    modal.appendChild(container);
    document.body.appendChild(modal);
    
    setTimeout(() => {
      progressBar.style.width = "100%";
    }, 100);
    
    this.fetchRealResult();
    
    const interval = setInterval(() => {
      const randomNumber = Math.floor(Math.random() * 101);
      rollNumber.textContent = randomNumber;
      
      const colorConfigs = [
        { color: "text-gray-400", glow: "shadow-[0_0_20px_rgba(255,255,255,0.5)]" },
        { color: "text-green-400", glow: "shadow-[0_0_20px_rgba(0,204,102,0.7)]" },
        { color: "text-blue-400", glow: "shadow-[0_0_20px_rgba(51,153,255,0.7)]" },
        { color: "text-purple-400", glow: "shadow-[0_0_20px_rgba(204,102,255,0.7)]" },
        { color: "text-yellow-400", glow: "shadow-[0_0_20px_rgba(255,204,0,0.7)]" },
        { color: "text-red-400", glow: "shadow-[0_0_20px_rgba(255,59,48,0.7)]" }
      ];
      const randomConfig = colorConfigs[Math.floor(Math.random() * colorConfigs.length)];
      rollNumber.className = "text-6xl font-extrabold text-center transition-all duration-0.3s " + randomConfig.color + " " + randomConfig.glow;
    }, 50);
    
    setTimeout(() => {
      clearInterval(interval);
      
      const finalNumber = this.realResult !== null ? this.realResult : Math.floor(Math.random() * 101);
      
      let finalColor = "";
      let quality = "";
      let numberColor = "";
      
      if (finalNumber >= 0 && finalNumber <= 20) {
        finalColor = "bg-gradient-to-r from-gray-500 to-gray-700";
        quality = "白色 - 普通";
        numberColor = "text-gray-400";
      } else if (finalNumber > 20 && finalNumber <= 40) {
        finalColor = "bg-gradient-to-r from-green-500 to-green-700";
        quality = "绿色 - 优秀";
        numberColor = "text-green-400";
      } else if (finalNumber > 40 && finalNumber <= 60) {
        finalColor = "bg-gradient-to-r from-blue-500 to-blue-700";
        quality = "蓝色 - 稀有";
        numberColor = "text-blue-400";
      } else if (finalNumber > 60 && finalNumber <= 70) {
        finalColor = "bg-gradient-to-r from-purple-500 to-purple-700";
        quality = "紫色 - 史诗";
        numberColor = "text-purple-400";
      } else if (finalNumber > 70 && finalNumber <= 89) {
        finalColor = "bg-gradient-to-r from-yellow-500 to-yellow-700";
        quality = "金色 - 传说";
        numberColor = "text-yellow-400";
      } else if (finalNumber >= 90 && finalNumber <= 100) {
        finalColor = "bg-gradient-to-r from-red-500 to-red-700";
        quality = "红色 - 神话";
        numberColor = "text-red-400";
      } else {
        finalColor = "bg-gradient-to-r from-purple-500 to-blue-500";
        quality = "蓝色 - 稀有";
        numberColor = "text-blue-400";
      }
      
      rollNumber.textContent = finalNumber;
      
      // 根据最终结果添加合适的发光效果
      let finalGlowEffect = "shadow-[0_0_20px_rgba(255,255,255,0.5)]";
      if (finalNumber >= 90) {
        finalGlowEffect = "shadow-[0_0_30px_rgba(255,0,51,0.8)]";
      } else if (finalNumber >= 70) {
        finalGlowEffect = "shadow-[0_0_25px_rgba(255,204,0,0.8)]";
      } else if (finalNumber >= 60) {
        finalGlowEffect = "shadow-[0_0_25px_rgba(204,102,255,0.8)]";
      } else if (finalNumber >= 40) {
        finalGlowEffect = "shadow-[0_0_25px_rgba(51,153,255,0.8)]";
      } else if (finalNumber >= 20) {
        finalGlowEffect = "shadow-[0_0_25px_rgba(0,204,102,0.8)]";
      }
      
      rollNumber.className = "text-6xl font-extrabold text-center transition-all duration-500 " + numberColor + " " + finalGlowEffect;
      
      // 为顶部长条添加发光效果和过渡动画
      const topBarClasses = "absolute top-0 left-0 right-0 h-1 " + finalColor + " transition-all duration-500";
      
      // 根据最终结果添加不同强度的发光效果
      let glowEffect = "shadow-lg";
      if (finalNumber >= 90) {
        glowEffect = "shadow-[0_0_25px_rgba(255,0,51,0.6)]";
      } else if (finalNumber >= 70) {
        glowEffect = "shadow-[0_0_20px_rgba(255,204,0,0.5)]";
      } else if (finalNumber >= 60) {
        glowEffect = "shadow-[0_0_15px_rgba(204,102,255,0.4)]";
      } else if (finalNumber >= 40) {
        glowEffect = "shadow-[0_0_15px_rgba(51,153,255,0.4)]";
      } else if (finalNumber >= 20) {
        glowEffect = "shadow-[0_0_15px_rgba(0,204,102,0.4)]";
      } else {
        glowEffect = "shadow-[0_0_15px_rgba(255,255,255,0.3)]";
      }
      
      topBar.className = topBarClasses + " " + glowEffect;
      
      // 更新进度条的最终颜色和发光效果
      progressBar.className = "h-full rounded-full transition-all duration-500 " + finalColor + " " + glowEffect;
      
      // 更新品质文本
      qualityText.className = "px-6 py-2 rounded-full text-lg font-semibold mb-6 inline-block mx-auto " + finalColor + " bg-opacity-30 text-white border " + finalColor.replace("from-", "border-").replace("to-", "border-") + " border-opacity-50 transition-all duration-500";
      qualityText.textContent = quality;
      
      setTimeout(() => {
        document.body.removeChild(modal);
        this.isAnimating = false;
        
        if (this.submitButton) {
          this.submitButton.textContent = this.originalText;
          this.submitButton.disabled = false;
        }
        
        window.location.reload();
      }, 1500);
    }, this.animationDuration);
  }
  
  fetchRealResult() {
    fetch(this.formAction, {
      method: "POST",
      body: this.formData
    })
    .then(function(response) {
      if (response.redirected) {
        return fetch(response.url);
      }
      return response;
    })
    .then(function(response) {
      return response.text();
    })
    .then(function(html) {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, "text/html");
      
      const resultRows = doc.querySelectorAll("table tbody tr");
      
      for (let i = 0; i < resultRows.length; i++) {
        const row = resultRows[i];
        const cells = row.querySelectorAll("td");
        if (cells.length >= 3) {
          const nameCell = cells[1];
          const numberCell = cells[2].querySelector("strong");
          
          if (nameCell && nameCell.textContent === this.playerName && numberCell) {
            this.realResult = parseInt(numberCell.textContent);
            break;
          }
        }
      }
    }.bind(this))
    .catch(function(error) {
      console.error("获取Roll点结果失败:", error);
    });
  }
}

const rollAnimation = new RollAnimation();

document.addEventListener("DOMContentLoaded", function() {
  const rollForm = document.querySelector(".roll-form");
  if (rollForm) {
    rollForm.addEventListener("submit", function(e) {
      const playerNameInput = document.getElementById("name");
      const playerName = playerNameInput ? playerNameInput.value : "匿名玩家";
      
      const submitButton = rollForm.querySelector("button[type='submit']");
      const originalText = submitButton.textContent;
      submitButton.textContent = "Roll点中...";
      submitButton.disabled = true;
      
      const formData = new FormData(rollForm);
      const formAction = rollForm.action;
      
      rollAnimation.showRollAnimation(playerName, submitButton, originalText, formData, formAction);
      
      e.preventDefault();
    });
  }
});
