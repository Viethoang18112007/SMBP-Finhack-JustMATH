import UIKit
import Capacitor

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard let windowScene = scene as? UIWindowScene else { return }

        window = UIWindow(windowScene: windowScene)
        window?.rootViewController = AppViewController()  // our subclass: it hands the phone id to the widget
        window?.makeKeyAndVisible()

        SceneDelegateProxy.shared.scene(scene, willConnectTo: session, options: connectionOptions)
        handleQuick(connectionOptions.urlContexts)  // launched by a tap on the Quick type bar widget
    }

    func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
        handleQuick(URLContexts)  // the app was already running
        SceneDelegateProxy.shared.scene(scene, openURLContexts: URLContexts)
    }

    // ssust://quick (the Quick type bar widget) opens the Quick type sheet with its field focused.
    private func handleQuick(_ contexts: Set<UIOpenURLContext>) {
        guard contexts.contains(where: { context in
            let url = context.url
            return url.scheme == "ssust" && url.host == "quick"
        }) else { return }
        (window?.rootViewController as? AppViewController)?.openQuickType()
    }

    func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
        SceneDelegateProxy.shared.scene(scene, continue: userActivity)
    }
}
